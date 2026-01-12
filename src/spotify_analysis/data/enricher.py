from abc import ABC, abstractmethod
from typing import Optional

import polars as pl
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy.exceptions import SpotifyOauthError

from .data_labels import DataLabels, SPOTIFY_LABELS


class Enricher(ABC):
    credential_fields: Optional[list[str]] = None
    
    @abstractmethod
    def enrich_data(self, data: pl.DataFrame) -> pl.DataFrame:
        pass
    
class SpotifyAPIEnricher(Enricher):
    credential_fields = ["SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET"]
    spotify: spotipy.Spotify = None
    
    def __init__(self):
        super().__init__()
        try:
            auth_manager = SpotifyClientCredentials()
        except SpotifyOauthError: # cant find SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET in environment
            return
        
        self.spotify = spotipy.Spotify(auth_manager=auth_manager)
        
    def enrich_data(self, data: pl.DataFrame) -> Optional[pl.DataFrame]:
        if self.spotify is None:
            return None
        
        track_uris = (
            data[SPOTIFY_LABELS[DataLabels.TRACK_ID]]
            .drop_nulls()
            .unique()
        )