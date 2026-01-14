from abc import ABC, abstractmethod
import json
import logging
from pathlib import Path
import time
from typing import Optional, Any

import sys

import polars as pl
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy.exceptions import SpotifyOauthError

from .data_labels import DataLabels, SPOTIFY_LABELS


logger = logging.getLogger(__name__)


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
        
        logger.debug(f"Found {len(uri_track_info_map)} tracks in cache...")
        
        return [
            uri_track_info_map[uri]
            for uri in track_uris
            if uri in uri_track_info_map
        ]
        
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