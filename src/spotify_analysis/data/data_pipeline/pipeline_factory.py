import io

from sqlalchemy.ext.asyncio import AsyncEngine

import polars as pl

from spotify_analysis.data.data_pipeline.pipelines import DataPipeline
from spotify_analysis.data.services import SpotifyAPITrack, SpotifyAPITracks
from spotify_analysis.data.data_pipeline.getter import IdentityGetter, SpotifyAPIGetter
from spotify_analysis.data.data_pipeline.parser import IdentityParser, SpotifyListeningHistoryParser
from spotify_analysis.data.data_pipeline.transformer import SpotifyListeningHistoryTransformer, SpotifyAPITransformer
from spotify_analysis.data.data_pipeline.loader import SpotifyListeningHistoryLoader, SpotifyAPILoader
from spotify_analysis.data.data_pipeline.listening_event import SpotifyListeningEventSchema


def spotify_listening_history_file_pipeline_factory(db_engine: AsyncEngine) -> DataPipeline[io.BytesIO, io.BytesIO, pl.DataFrame, SpotifyListeningEventSchema]:
    return DataPipeline(
        getter=IdentityGetter[io.BytesIO](),
        parser=SpotifyListeningHistoryParser(),
        transformer=SpotifyListeningHistoryTransformer(),
        loader=SpotifyListeningHistoryLoader(db_engine),
    )
    
def spotify_api_pipeline_factory(db_engine: AsyncEngine) -> DataPipeline[str, SpotifyAPITracks, SpotifyAPITracks, SpotifyAPITrack]:
    return DataPipeline(
        getter=SpotifyAPIGetter(),
        parser=IdentityParser(),
        transformer=SpotifyAPITransformer(),
        loader=SpotifyAPILoader(db_engine),
    )