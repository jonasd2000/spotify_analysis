from abc import ABC, abstractmethod
import asyncio
from pathlib import Path
from typing import Any

import polars as pl

from spotify_analysis.data.worker import Worker
from spotify_analysis.data.data_labels import (
    SPOTIFY_LABELS,
    DataLabels,
    fill_template,
)

class Parser[I, O](ABC):
    batch_size: int
    num_workers: int
    
    def __init__(self, num_workers: int = 1, batch_size: int = 1):
        super().__init__()
        self.num_workers = num_workers
        self.batch_size = batch_size
    
    @abstractmethod
    async def _parse_items(self, items: list[I], output_queue: asyncio.Queue[O]) -> None:
        ...
    
    async def parse_data(self, input_queue: asyncio.Queue[I], output_queue: asyncio.Queue[O]) -> None:
        with asyncio.TaskGroup() as tg:
            for _ in range(self.num_workers):
                tg.create_task(self._parse_items(input_queue, output_queue, self.batch_size))
        output_queue.shutdown()
    
class JsonParser(Parser):
    schema: dict
    
    async def _parse_items(self, items: list[str], output_queue: asyncio.Queue[dict[str, Any]]) -> None:
        for item in items:
            await output_queue.put(pl.read_json(item, schema=self.schema))

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
    