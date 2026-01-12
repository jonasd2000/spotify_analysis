from abc import ABC, abstractmethod

import polars as pl
import spotipy

from .data_labels import DataLabels


class Enricher(ABC):
    @abstractmethod
    def enrich_data(self, data: pl.DataFrame) -> pl.DataFrame:
        pass
    
class SpotifyAPIEnricher(Enricher):
    def enrich_data(self, data: pl.DataFrame) -> pl.DataFrame:
        track_uris = (
            data[DataLabels.TRACK_ID.value]
            .drop_nulls()
            .unique()
        )