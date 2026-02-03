import io

from sqlalchemy.ext.asyncio import AsyncEngine

import polars as pl

from spotify_analysis.data.data_pipeline.pipelines import PipelineModule
from spotify_analysis.data.data_pipeline.getter import SpotifyAPIGetter
from spotify_analysis.data.data_pipeline.parser import SpotifyListeningHistoryParser
from spotify_analysis.data.data_pipeline.transformer import SpotifyListeningHistoryTransformer, SpotifyAPITransformer
from spotify_analysis.data.data_pipeline.loader import SpotifyListeningHistoryLoader, SpotifyAPILoader

def spotify_listening_history_file_pipeline_module_factory(db_engine: AsyncEngine) -> PipelineModule:
    return PipelineModule([
        SpotifyListeningHistoryParser(batch_size=1, num_workers=5, strict=False),
        SpotifyListeningHistoryTransformer(batch_size=1, num_workers=5, strict=False),
        SpotifyListeningHistoryLoader(db_engine, num_workers=1),
    ])
    
def spotify_api_pipeline_module_factory(db_engine: AsyncEngine) -> PipelineModule:
    return PipelineModule([
        SpotifyAPIGetter(),
        SpotifyAPITransformer(batch_size=5, num_workers=1, strict=False),
        SpotifyAPILoader(db_engine, num_workers=1),
    ])