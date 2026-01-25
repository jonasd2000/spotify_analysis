from abc import ABC, abstractmethod
import asyncio

import polars as pl

from spotify_analysis.data.worker import Worker
from .listening_event import spotify_listening_event_pl_schema, MediaType

class DataTransformer[I, O](ABC):
    batch_size: int
    num_workers: int
    
    def __init__(self, batch_size: int = 1, num_workers: int = 1):
        super().__init__()
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0")
        if num_workers <= 0:
            raise ValueError("num_workers must be greater than 0")
        self.batch_size = batch_size
        self.num_workers = num_workers
    
    @abstractmethod
    async def _transform_item(self, item: I) -> O:
        pass
    
    async def _transform_batch(self, items: list[I], output_queue: asyncio.Queue[O]) -> None:
        for item in items:
            processed_item = await self._transform_item(item, output_queue)
            await output_queue.put(processed_item)
    
    async def transform_data(self, input_queue: asyncio.Queue[I], output_queue: asyncio.Queue[O]) -> None:
        worker = Worker(input_queue, self.batch_size, strict=True, batch_processor=self._transform_batch)
        async with asyncio.TaskGroup() as tg:
            for _ in range(self.num_workers):
                tg.create_task(worker(output_queue=output_queue))
        output_queue.shutdown()
    
class DataTransformerPipeline[I, O](DataTransformer):
    def __init__(self, transformers: list[DataTransformer], batch_size: int = 100, num_workers: int = 1) -> None:
        super().__init__(batch_size, num_workers)
        self.transformers = transformers
        
    async def _transform_batch(self, items: list[I], output_queue: asyncio.Queue[O]) -> None:
        transform_queues = [asyncio.Queue() for _ in range(len(self.transformers))]
        transform_queues += [output_queue]
        
        async with asyncio.TaskGroup() as tg:
            for i, transformer in enumerate(self.transformers):
                tg.create_task(transformer.transform_data(transform_queues[i], transform_queues[i+1]))
                
        for item in items:
            await transform_queues[0].put(item)
    
class SchemaTransformer(DataTransformer):
    old_schema: pl.Schema
    new_schema: pl.Schema
        
    def __init__(self, old_schema: dict[str, pl.DataType], new_schema: dict[str, pl.DataType]) -> None:
        self.old_schema = old_schema
        self.new_schema = new_schema
        self.schema_mapping = {
            (old_name, old_type): (new_name, new_type) 
            for (old_name, old_type), (new_name, new_type) in zip(old_schema.items(), new_schema.items())
        }
        
    async def _transform_item(self, df: pl.DataFrame) -> pl.DataFrame:
        for current_column_name, current_column_dtype in df.schema.items():
            new_column_name, new_column_dtype = self.schema_mapping[(current_column_name, current_column_dtype)]
            
            df = df.with_columns(
                pl.col(current_column_name).cast(new_column_dtype).alias(new_column_name)
            )
            
            if new_column_name != current_column_name:
                df = df.drop(current_column_name)
            
        return df
        
class SpotifyListeningHistoryTransformer(DataTransformer):
    def _transform_item(self, lh_data: pl.DataFrame) -> pl.DataFrame:
        # turns spotify data into listening events
        # 1. create column  track_type 
        #    based on       which column of master_metadata_track_name, episode_name, audiobook_chapter_title has a non null value
        lh_data = lh_data.with_columns(
            (
                pl.when(pl.col("master_metadata_track_name").is_not_null())
                  .then(pl.lit(MediaType.MUSIC_TRACK, dtype=MediaType))
                
                  .when(pl.col("episode_name").is_not_null())
                  .then(pl.lit(MediaType.PODCAST_EPISODE, dtype=MediaType))
                
                  .when(pl.col("audiobook_chapter_title").is_not_null())
                  .then(pl.lit(MediaType.AUDIOBOOK_CHAPTER, dtype=MediaType))
                
                  .otherwise(None)
                  .alias("media_type")
            )
        )
        
        # 2. merge columns  master_metadata_track_name, episode_name, audiobook_chapter_title 
        #    into           track_name
        lh_data = lh_data.with_columns(
            pl.col("master_metadata_track_name").fill_null(pl.col("episode_name")).fill_null(pl.col("audiobook_chapter_title")).alias("track_name")
        ).drop("master_metadata_track_name", "episode_name", "audiobook_chapter_title")
        
        # 3. merge columns  master_metadata_album_album_name, episode_show_name, audiobook_title 
        #    into           collection_name
        lh_data = lh_data.with_columns(
            pl.col("master_metadata_album_album_name").fill_null(pl.col("episode_show_name")).fill_null(pl.col("audiobook_title")).alias("collection_name")
        ).drop("master_metadata_album_album_name", "episode_show_name", "audiobook_title")
        # 4. merge columns  spotify_track_uri, spotify_episode_uri, audiobook_chapter_uri 
        #    into           spotify_track_id
        lh_data = lh_data.with_columns(
            pl.col("spotify_track_uri").fill_null(pl.col("spotify_episode_uri")).fill_null(pl.col("audiobook_chapter_uri")).alias("spotify_track_id")
        ).drop("spotify_track_uri", "spotify_episode_uri", "audiobook_chapter_uri")
        
        # 5. turn ts into datetime
        lh_data = lh_data.with_columns(
            pl.col("ts").str.to_datetime("%Y-%m-%dT%H:%M:%SZ")
        )
        
        # 6. rename ts                                 to timestamp
        #    rename master_metadata_album_artist_name  to creator
        #    rename conn_country                       to country
        #    rename ip_addr                            to ip_address
        lh_data = lh_data.rename({
            "ts": "timestamp", 
            "master_metadata_album_artist_name": "creators",
            "conn_country": "country",
            "ip_addr": "ip_address"
        })
        
        # 7. turn creators column into list of string current: "artist", wanted ["artist"] and if null: current: null wanted []
        lh_data = lh_data.with_columns(
            pl.when(pl.col("creators").is_not_null())
            .then(pl.concat_list(pl.col("creators")))
            .otherwise(pl.lit([]))
            .alias("creators")
        )
        
        # # order the columns
        lh_data = lh_data.select([c for c in spotify_listening_event_pl_schema])
        
        return lh_data
        