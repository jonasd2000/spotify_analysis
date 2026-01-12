from abc import ABC, abstractmethod
from typing import Optional

import polars as pl
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from .data_labels import DataLabels


class Enricher(ABC):
    credential_fields: Optional[list[str]] = None
    
    @abstractmethod
    def enrich_data(self, data: pl.DataFrame) -> pl.DataFrame:
        pass
    
class SpotifyAPIEnricher(Enricher):
    credential_fields = ["SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET"]
    spotify = spotipy.Spotify()
    
    
    def __init__(self):
        super().__init__()
        auth_manager = SpotifyClientCredentials()
        self.spotify = spotipy.Spotify(auth_manager=auth_manager)
        
    def enrich_data(self, data: pl.DataFrame) -> pl.DataFrame:
        track_uris = (
            data[DataLabels.TRACK_ID.value]
            .drop_nulls()
            .unique()
        )