from abc import ABC, abstractmethod
import httpx
import json
import logging
from pathlib import Path
import time
from typing import Optional, Any

import polars as pl

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy.exceptions import SpotifyOauthError

from .data_labels import DataLabels, SPOTIFY_LABELS


logger = logging.getLogger(__name__)


def retry(func, *args, retries: int=3, delay: float=1, backoff: Optional[float]=2, on_exceptions: Optional[list[type[Exception]]]=None, **kwargs):
    def wrapper(*args, **kwargs):
        for i in range(retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if (on_exceptions is not None) and (type(e) not in on_exceptions):
                    raise
                sleep_time = delay * ((backoff or 1) ** i)
                logger.debug(f"Retrying {func.__name__} in {sleep_time} seconds...")
                time.sleep(sleep_time)
    return wrapper


class Enricher(ABC):
    credential_fields: Optional[list[str]] = None
    
    @abstractmethod
    async def enrich_data(self, data: pl.DataFrame) -> pl.DataFrame:
        pass
    
class SpotifyAPIEnricher(Enricher):
    credential_fields = ["SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET"]
    
    api_tracks_request_batch_size = 50
    api_request_retries = 3
    
    cache_path = Path("spotify_api_cache.json")
    
    spotify: spotipy.Spotify = None
    
    def __init__(self):
        super().__init__()
        try:
            auth_manager = SpotifyClientCredentials()
        except SpotifyOauthError: # cant find SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET in environment
            return
        
        self.spotify = spotipy.Spotify(auth_manager=auth_manager)
        
    @retry
    def get_tracks_info_from_api(self, track_uris: list[str], retries: Optional[int] = 3) -> list[dict[str, Any]]:
        try_no = 0
        retries = retries if retries is not None else -1 # if retries is None, infinite
        logger.debug(f"Getting tracks info for {len(track_uris)} tracks, retries: {retries}...")
        while try_no < retries:
            try_no += 1
            try:
                tracks_info_response: list[dict[str, Any]] = self.spotify.tracks(track_uris)
                tracks_info = [
                    {
                        "album": {
                            "name": track_info["album"]["name"],
                            "uri": track_info["album"]["uri"],
                            "album_type": track_info["album"]["album_type"],
                            "total_tracks": track_info["album"]["total_tracks"],
                            "release_date": track_info["album"]["release_date"],
                            "release_date_precision": track_info["album"]["release_date_precision"],
                        },
                        "artists": [
                            {
                                "name": artist["name"],
                                "uri": artist["uri"],
                            }
                            for artist in track_info["artists"]
                        ],
                        "duration_ms": track_info["duration_ms"],
                        "explicit": track_info["explicit"],
                        "isrc": track_info["external_ids"].get("isrc"),
                        "name": track_info["name"],
                        "uri": track_info["uri"],
                    }
                    for track_info in tracks_info_response["tracks"]
                ]
                return tracks_info
            except spotipy.SpotifyException as e:
                if e.http_status == 429: # too many requests
                    if "Retry-After" in e.headers:
                        retry_after = int(e.headers["Retry-After"])
                        logger.debug(f"Spotify API rate limit exceeded. Retrying in {retry_after} seconds...")
                        time.sleep(retry_after)
        
    def get_tracks_info_from_cache(self, track_uris: list[str]) -> list[dict[str, Any]]:
        logger.debug(f"Getting tracks info from cache for {len(track_uris)} tracks...")
        if not self.cache_path.exists():
            return []
        
        with self.cache_path.open("r") as f:
            uri_track_info_map = json.load(f)
        
        tracks_info = [
            uri_track_info_map[uri]
            for uri in track_uris
            if uri in uri_track_info_map
        ]
        
        logger.debug(f"Found {len(tracks_info)}/{len(track_uris)} tracks in cache...")
        
        return tracks_info
        
    def write_tracks_info_to_cache(self, tracks_info: list[dict[str, Any]]):
        logger.debug(f"Writing {len(tracks_info)} tracks info to cache...")
        
        uri_track_info_map = {
            track_info["uri"]: track_info
            for track_info in tracks_info
        }
        
        if self.cache_path.exists():
            with self.cache_path.open("r") as f:
                uri_track_info_map.update(json.load(f))
        
        with self.cache_path.open("w") as f:
            json.dump(uri_track_info_map, f)
        
    async def enrich_data(self, data: pl.DataFrame) -> Optional[pl.DataFrame]:
        if self.spotify is None:
            return None
        
        track_uris = (
            data[SPOTIFY_LABELS[DataLabels.TRACK_ID]]
            .drop_nulls()
            .unique()
        )
        
        tracks_info_from_cache = self.get_tracks_info_from_cache(track_uris)
        track_uris_in_cache = [track_info["uri"] for track_info in tracks_info_from_cache]
        
        remaining_track_uris = list(set(track_uris) - set(track_uris_in_cache))
        
        batch_size = SpotifyAPIEnricher.api_tracks_request_batch_size
        remaining_track_uris_batches = [
            remaining_track_uris[i:i + batch_size] 
            for i in range(0, len(remaining_track_uris), batch_size)
        ]
        
        tracks_info_from_api = []
        
        for track_uris_batch in remaining_track_uris_batches:
            track_info_batch = self.get_tracks_info_from_api(track_uris_batch, self.api_request_retries)
            tracks_info_from_api.extend(track_info_batch)
        
        self.write_tracks_info_to_cache(tracks_info_from_api)
        
        tracks_info = tracks_info_from_cache + tracks_info_from_api
        
        return pl.DataFrame(tracks_info)
    
    
class MusicbrainzAPIEnricher(Enricher):
    user_agent = "musicbrainz-api-enricher/0.0.1"
    api_batch_size = 100
    
    def __init__(self):
        super().__init__()
        self.headers = {
            "User-Agent": MusicbrainzAPIEnricher.user_agent,
            "Accept": "application/json"
        }
    
    @retry
    async def get_genre_names(self, client: httpx.AsyncClient) -> list[str]:
        response = await client.get("https://musicbrainz.org/ws/2/genre/all?fmt=txt")
        if response.status_code == 200:
            newline_seperated_genres = response.text
            genres = newline_seperated_genres.split("\n")
            return genres
        else:
            raise Exception("Failed to get genres from musicbrainz")
    
    @retry
    async def get_record_by_isrc(self, client: httpx.AsyncClient, isrc: str) -> Optional[dict[str, Any]]:
        response = await client.get(f"https://musicbrainz.org/ws/2/isrc/{isrc}")
        if response.status_code == 200:
            return response.json()["recordings"][0]
        else:
            raise Exception(f"Failed to get record from musicbrainz for isrc {isrc}")
    
    @retry
    async def get_records_by_isrcs(self, client: httpx.AsyncClient, isrcs: list[str]) -> list[dict[str, Any]]:
        isrc_string = " OR ".join([f"isrc:{isrc}" for isrc in isrcs])
        response = await client.get(f"https://musicbrainz.org/ws/2/recording?query={isrc_string}&limit={len(isrcs)}")
        if response.status_code == 200:
            return response.json()["recordings"]
        else:
            raise Exception(f"Failed to get records from musicbrainz for isrcs {','.join(isrcs)}")
    
    def match_genres(self, recordings: list[dict[str, Any]], genres: list[str]):
        for recording in recordings:
            tags = recording.get("tags", [])
            genre_tags = filter(lambda tag: tag["name"] in genres, tags)
            recording_genres = map(lambda tag: tag["name"], genre_tags)
            recording["genres"] = list(recording_genres)
    
    async def enrich_data(self, data: pl.DataFrame) -> Optional[pl.DataFrame]:
        if "isrc" not in data.columns:
            return None
        
        isrcs = data["isrc"].drop_nulls().unique()
        
        recordings = []
        async with httpx.AsyncClient(headers=self.headers) as client:
            genres = await self.get_genre_names(client)
            for batch_index, isrc_index in enumerate(range(0, len(isrcs), MusicbrainzAPIEnricher.api_batch_size)):
                isrc_batch = isrcs[isrc_index:isrc_index + MusicbrainzAPIEnricher.api_batch_size]
                recordings_batch = await self.get_records_by_isrcs(client, isrc_batch)
                recordings.extend(recordings_batch)
                logger.debug(f"Got {len(recordings_batch)} recordings in batch {batch_index+1}/{len(isrcs) // MusicbrainzAPIEnricher.api_batch_size}")
        
        self.match_genres(recordings, genres)
        
        recordings_df = pl.DataFrame(recordings)
        recordings_df = recordings_df.explode("isrcs").rename({"isrcs": "isrc"})
        recordings_df = recordings_df.unique(subset="isrc", keep="first")
        
        enriched = data.join(recordings_df, on="isrc", how="left", suffix="_enriched")
        
        return enriched