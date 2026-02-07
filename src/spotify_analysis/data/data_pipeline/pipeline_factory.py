from sqlalchemy.ext.asyncio import AsyncEngine

import polars as pl

from spotify_analysis.data.data_pipeline.pipelines import PipelineModule, AsyncPipelineStage
from spotify_analysis.data.data_pipeline.getter import SpotifyAPIGetter
from spotify_analysis.data.data_pipeline.parser import SpotifyListeningHistoryParser
from spotify_analysis.data.data_pipeline.transformer import SpotifyListeningHistoryTransformer, SpotifyAPITransformer, DataTransformerPipeline, UniqueTransformer, ApplyFunctionTransformer
from spotify_analysis.data.data_pipeline.loader import SpotifyListeningHistoryLoader, SpotifyAPILoader

def spotify_listening_history_file_pipeline_module_factory(db_engine: AsyncEngine) -> PipelineModule:
    return PipelineModule([
        SpotifyListeningHistoryParser(batch_size=1, num_workers=5, strict=False),
        SpotifyListeningHistoryTransformer(batch_size=1, num_workers=5, strict=False),
        SpotifyListeningHistoryLoader(db_engine, num_workers=1),
    ])
    
def unique_spotify_uris_pipeline_module_factory() -> PipelineModule:
    df_unique_uris_stage = ApplyFunctionTransformer[pl.DataFrame, str](batch_size=1, num_workers=1, strict=False, function=lambda df: df["spotify_track_uri"].unique())
    df_unique_uris_stage.unpack_transformed_item = True
    return PipelineModule([df_unique_uris_stage])
    
def spotify_api_pipeline_module_factory(db_engine: AsyncEngine, spotify_listening_history_loader: AsyncPipelineStage) -> PipelineModule:
    spt_listening_history_loader_finished = spotify_listening_history_loader.finished_event
    return PipelineModule([
        SpotifyAPIGetter(),
        SpotifyAPITransformer(batch_size=5, num_workers=1, strict=False),
        SpotifyAPILoader(db_engine, num_workers=1, wait_for=spt_listening_history_loader_finished),
    ])