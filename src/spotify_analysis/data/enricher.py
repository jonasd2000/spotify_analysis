from abc import ABC, abstractmethod
import logging
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
    def enrich_data(self, data: pl.DataFrame) -> pl.DataFrame:
        pass
    
class SpotifyAPIEnricher(Enricher):
    credential_fields = ["SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET"]
    api_tracks_request_batch_size = 50
    api_request_retries = 3
    spotify: spotipy.Spotify = None
    
    def __init__(self):
        super().__init__()
        try:
            auth_manager = SpotifyClientCredentials()
        except SpotifyOauthError: # cant find SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET in environment
            return
        
        self.spotify = spotipy.Spotify(auth_manager=auth_manager)
        
        
    def get_tracks_info(self, track_uris: list[str], retries: Optional[int] = 3) -> list[dict[str, Any]]:
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
        
        
    def enrich_data(self, data: pl.DataFrame) -> Optional[pl.DataFrame]:
        if self.spotify is None:
            return None
        
        track_uris = (
            data[SPOTIFY_LABELS[DataLabels.TRACK_ID]]
            .drop_nulls()
            .unique()
        )
        
        batch_size = SpotifyAPIEnricher.api_tracks_request_batch_size
        track_uris = [
            track_uris[i:i + batch_size] 
            for i in range(0, len(track_uris), batch_size)
        ]
        
        tracks_info = []
        for track_uris_batch in track_uris:
            track_info_batch = self.get_tracks_info(track_uris_batch, self.api_request_retries)
            tracks_info.extend(track_info_batch)
        
        return pl.DataFrame(tracks_info)