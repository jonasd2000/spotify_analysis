import io
import json
from pathlib import Path

import polars as pl

from spotify_analysis.data.data_pipeline.pipeline_stage import AsyncPipelineStage
from spotify_analysis.data.worker import Worker
from spotify_analysis.data.data_labels import (
    SPOTIFY_LABELS,
    DataLabels,
    fill_template,
)

class Parser[I, O](AsyncPipelineStage[I, O]):
    pass
    
class IdentityParser[I](Parser[I, I]):
    async def _process_item(self, item: I) -> I:
        return item
    
class JsonParser(Parser[str | Path | io.IOBase | bytes, pl.DataFrame]):
    schema: dict
    
    async def _process_item(self, item: str | Path | io.IOBase | bytes) -> pl.DataFrame:
        return pl.read_json(item, schema=self.schema)

class SchemaTemplateMixIn:
    schema_template: dict
    
    def __init__(self):
        self.schema = fill_template(self.schema_template, SPOTIFY_LABELS)

class SpotifyListeningHistoryParser(JsonParser, SchemaTemplateMixIn):
    schema_template = {
        DataLabels.TIMESTAMP: pl.String,
        DataLabels.PLATFORM: pl.String,
        DataLabels.MILLISECONDS_PLAYED: pl.UInt32,
        DataLabels.COUNTRY: pl.String,
        DataLabels.IP_ADDRESS: pl.String,
        DataLabels.TRACK_NAME: pl.String,
        DataLabels.ARTIST: pl.String,
        DataLabels.ALBUM_NAME: pl.String,
        DataLabels.TRACK_ID: pl.String,
        #   "user_agent_decrypted": pl.String,
        DataLabels.PODCAST_EPISODE_NAME: pl.String,
        DataLabels.PODCAST_NAME: pl.String,
        DataLabels.PODCAST_EPISODE_ID: pl.String,
        DataLabels.AUDIOBOOK_TITLE: pl.String,
        DataLabels.AUDIOBOOK_CHAPTER_ID: pl.String,
        DataLabels.AUDIOBOOK_CHAPTER_TITLE: pl.String,
        DataLabels.REASON_START: pl.String,
        DataLabels.REASON_END: pl.String,
        DataLabels.SHUFFLE: pl.Boolean,
        DataLabels.SKIPPED: pl.Boolean,
        DataLabels.OFFLINE: pl.Boolean,
        DataLabels.OFFLINE_TIMESTAMP: pl.String,
        DataLabels.INCOGNITO_MODE: pl.Boolean,
    }
    