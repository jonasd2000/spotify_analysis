from abc import ABC, abstractmethod

import polars as pl
from poldantic import to_polars_schema

from .listening_event import spotify_listening_event_pl_schema, TrackType


class DataValidationError(Exception):
    pass

class DataTransformer(ABC):
    @abstractmethod
    def _transform_data(self, data: pl.DataFrame) -> pl.DataFrame:
        pass
    
    def validate_input_data(self, data: pl.DataFrame) -> None:
        pass
    
    def validate_output_data(self, data: pl.DataFrame) -> None:
        pass
    
    def transform_data(self, data: pl.DataFrame) -> pl.DataFrame:
        try:
            self.validate_input_data(data)
        except DataValidationError as e:
            raise e
        
        transformed_data = self._transform_data(data)
        
        try: 
            self.validate_output_data(transformed_data)
        except DataValidationError as e:
            raise e
        
        return transformed_data
    
class DataTransformerPipeline(DataTransformer):
    def __init__(self, transformers: list[DataTransformer]) -> None:
        self.transformers = transformers
        
    def _transform_data(self, data: pl.DataFrame) -> pl.DataFrame:
        for transformer in self.transformers:
            data = transformer.transform_data(data)
        return data
    
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
        
    def validate_input_data(self, data):
        if data.schema != self.old_schema:
            raise DataValidationError("Data schema does not match expected schema")
        
    def validate_output_data(self, data):
        if data.schema != self.new_schema:
            raise DataValidationError("Data schema does not match expected schema")
        
    def _transform_data(self, data: pl.DataFrame) -> pl.DataFrame:
        for current_column_name, current_column_dtype in data.schema.items():
            new_column_name, new_column_dtype = self.schema_mapping[(current_column_name, current_column_dtype)]
            
            data = data.with_columns(
                pl.col(current_column_name).cast(new_column_dtype).alias(new_column_name)
            )
            
            if new_column_name != current_column_name:
                data = data.drop(current_column_name)
        return data
        
class SpotifyDataTransformer(DataTransformer):
    def validate_input_data(self, data):
        # validate that input data conforms to expected spotify data schema
        pass
    
    def validate_output_data(self, data):
        if not (data.schema == spotify_listening_event_pl_schema):
            raise DataValidationError(f"Schema {data.schema} does not match expected schema {spotify_listening_event_pl_schema}")
    
    def _transform_data(self, data: pl.DataFrame) -> pl.DataFrame:
        # turns spotify data into listening events
        # 1. create column  track_type 
        #    based on       which column of master_metadata_track_name, episode_name, audiobook_chapter_title has a non null value
        data = data.with_columns(
            (
                pl.when(pl.col("master_metadata_track_name").is_not_null())
                  .then(pl.lit(TrackType.SONG, dtype=TrackType))
                
                  .when(pl.col("episode_name").is_not_null())
                  .then(pl.lit(TrackType.PODCAST_EPISODE, dtype=TrackType))
                
                  .when(pl.col("audiobook_chapter_title").is_not_null())
                  .then(pl.lit(TrackType.AUDIOBOOK_CHAPTER, dtype=TrackType))
                
                  .otherwise(None)
                  .alias("track_type")
            )
        )
        
        # 2. merge columns  master_metadata_track_name, episode_name, audiobook_chapter_title 
        #    into           track_name
        data = data.with_columns(
            pl.col("master_metadata_track_name").fill_null(pl.col("episode_name")).fill_null(pl.col("audiobook_chapter_title")).alias("track_name")
        ).drop("master_metadata_track_name", "episode_name", "audiobook_chapter_title")
        
        # 3. merge columns  master_metadata_album_album_name, episode_show_name, audiobook_title 
        #    into           collection_name
        data = data.with_columns(
            pl.col("master_metadata_album_album_name").fill_null(pl.col("episode_show_name")).fill_null(pl.col("audiobook_title")).alias("collection_name")
        ).drop("master_metadata_album_album_name", "episode_show_name", "audiobook_title")
        # 4. merge columns  spotify_track_uri, spotify_episode_uri, audiobook_chapter_uri 
        #    into           spotify_track_id
        data = data.with_columns(
            pl.col("spotify_track_uri").fill_null(pl.col("spotify_episode_uri")).fill_null(pl.col("audiobook_chapter_uri")).alias("spotify_track_id")
        ).drop("spotify_track_uri", "spotify_episode_uri", "audiobook_chapter_uri")
        
        # 5. turn ts into datetime
        data = data.with_columns(
            pl.col("ts").str.to_datetime("%Y-%m-%dT%H:%M:%SZ")
        )
        
        # 6. rename ts                                 to timestamp
        #    rename master_metadata_album_artist_name  to creator
        #    rename conn_country                       to country
        #    rename ip_addr                            to ip_address
        data = data.rename({
            "ts": "timestamp", 
            "master_metadata_album_artist_name": "creators",
            "conn_country": "country",
            "ip_addr": "ip_address"
        })
        
        # 7. turn creators column into list of string current: "artist", wanted ["artist"]
        data = data.with_columns(
            pl.concat_list(pl.col("creators")).alias("creators")
        )
        
        # order the columns
        data = data.select([c for c in spotify_listening_event_pl_schema])
        
        return data
        