import asyncio
import logging
from typing import Callable

import polars as pl

from spotify_analysis.data.data_pipeline.pipeline_stage import AsyncPipelineStage
from spotify_analysis.data.services import SpotifyAPITracks, SpotifyAPITrack
from .listening_event import spotify_listening_event_pl_schema, MediaType


logger = logging.getLogger(__name__)


class DataTransformer[I, O](AsyncPipelineStage[I, O]):
    unpack_transformed_item: bool = False
    
    async def _put_processed_item_to_queue(self, processed_item, output_queue):
        if self.unpack_transformed_item:
            for item in processed_item:
                await output_queue.put(item)
        else:
            await output_queue.put(processed_item)
    
class IdentityTransformer[I](DataTransformer[I, I]):
    async def _process_item(self, item: I) -> I:
        return item
    
class ApplyFunctionTransformer[I, O](DataTransformer[I, O]):
    function: Callable[[I], O]
    
    def __init__(self, batch_size: int, num_workers: int, strict: bool, function: Callable[[I], O]):
        super().__init__(batch_size, num_workers, strict)
        self.function = function
        
    async def _process_item(self, item: I) -> O:
        return self.function(item)
        
class UniqueTransformer[I, O](DataTransformer[I, O]):
    processed_items: set[O]
    
    def __init__(self, batch_size, num_workers, strict):
        super().__init__(batch_size, num_workers, strict)
        self.processed_items = set()
        
    async def _process_item(self, item: I) -> O | None:
        if item in self.processed_items:
            return None
        else:
            self.processed_items.add(item)
            return item
        
    async def _put_processed_item_to_queue(self, processed_item: O | None, output_queue: asyncio.Queue[O]):
        if processed_item is not None:
            await output_queue.put(processed_item)
        
class DataTransformerPipeline[I, O](DataTransformer[I, O]):
    def __init__(self, transformers: list[DataTransformer], batch_size: int = 100, num_workers: int = 1) -> None:
        super().__init__(batch_size, num_workers)
        self.transformers = transformers
        
    async def _process_items(self, items, output_queue):
        transform_queues = [asyncio.Queue() for _ in range(len(self.transformers))]
        transform_queues += [output_queue]
        
        async with asyncio.TaskGroup() as tg:
            for i, transformer in enumerate(self.transformers):
                tg.create_task(transformer.transform_data(transform_queues[i], transform_queues[i+1]))
                
        for item in items:
            await transform_queues[0].put(item)
    
class SchemaTransformer(DataTransformer[pl.DataFrame, pl.DataFrame]):
    old_schema: pl.Schema
    new_schema: pl.Schema
        
    def __init__(self, old_schema: dict[str, pl.DataType], new_schema: dict[str, pl.DataType], batch_size: int = 1, num_workers: int = 1, strict: bool = False) -> None:
        super().__init__(batch_size, num_workers, strict)
        self.old_schema = old_schema
        self.new_schema = new_schema
        self.schema_mapping = {
            (old_name, old_type): (new_name, new_type) 
            for (old_name, old_type), (new_name, new_type) in zip(old_schema.items(), new_schema.items())
        }
        
    async def _process_item(self, df: pl.DataFrame) -> pl.DataFrame:
        for current_column_name, current_column_dtype in df.schema.items():
            new_column_name, new_column_dtype = self.schema_mapping[(current_column_name, current_column_dtype)]
            
            df = df.with_columns(
                pl.col(current_column_name).cast(new_column_dtype).alias(new_column_name)
            )
            
            if new_column_name != current_column_name:
                df = df.drop(current_column_name)
            
        return df
        
        
from .listening_event import SpotifyListeningEventSchema        

class SpotifyListeningHistoryTransformer(DataTransformer[pl.DataFrame, SpotifyListeningEventSchema]):
    unpack_transformed_item: bool = True
    
    async def _process_item(self, lh_data: pl.DataFrame) -> list[SpotifyListeningEventSchema]:
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
        
        
        listening_event_schemas = [
            SpotifyListeningEventSchema(**listening_event) for listening_event in lh_data.iter_rows(named=True)
        ]
        
        return listening_event_schemas
        
class SpotifyAPITransformer(DataTransformer[SpotifyAPITracks, SpotifyAPITrack]):
    unpack_transformed_item: bool = True
    
    async def _process_item(self, response: SpotifyAPITracks) -> list[SpotifyAPITrack]:
        logger.debug(f"Processing Spotify API response...")
        tracks_list = response["tracks"]
        return tracks_list