from pathlib import Path
import os

import polars as pl

class GroupByAggregateParser:
    aggregate_choices = [
        "count",
        "sum",
        "min",
        "max",
        "mean",
    ]
    
    group_by: str
    aggregate_function: str
    aggregate_by: str
    
    def __init__(self) -> None:
        self.group_by = ""
        self.aggregate_function = ""
        self.aggregate_by = ""
        
    def set_group_by(self, group_by: str) -> None:
        self.group_by = group_by
        
    def process_group_by_change_event(self, event) -> None:
        self.set_group_by(event.value)
        
    def get_group_by_expression(self) -> pl.Expr:
        if not self.group_by:
            return None
        return pl.col(self.group_by)
        
    def set_aggregate_function(self, aggregate_function: str) -> None:
        self.aggregate_function = aggregate_function
        
    def process_aggregate_function_change_event(self, event) -> None:
        self.set_aggregate_function(event.value)
        
    def set_aggregate_by(self, aggregate_by: str) -> None:
        self.aggregate_by = aggregate_by
        
    def process_aggregate_by_change_event(self, event) -> None:
        self.set_aggregate_by(event.value)

    def get_aggregate_expression(self) -> pl.Expr:
        # aggregate functions that don't need a column
        match self.aggregate_function:
            case "count":
                return pl.count()
            case _:
                pass
        
        if self.aggregate_by == "":
            return None
        
        # aggregate functions that need a column to aggregate
        match self.aggregate_function:
            case "sum":
                return pl.col(self.aggregate_by).sum()
            case "min":
                return pl.col(self.aggregate_by).min()
            case "max":
                return pl.col(self.aggregate_by).max()
            case "mean":
                return pl.col(self.aggregate_by).mean()
            case _:
                return None
        

AUDIO_STREAMING_HISTORY_FILENAME_START = 'Streaming_History_Audio'

class DataManager:
    group_by_aggregate_parser: GroupByAggregateParser
    
    path: Path
    full_data: pl.DataFrame
    
    def __init__(self) -> None:
        self.group_by_aggregate_parser = GroupByAggregateParser()
        self.path = Path()
    
    def is_audio_streaming_history_file(self, path: Path, filename: str) -> bool:
        return  os.path.isfile(path / filename) and\
                filename.startswith(AUDIO_STREAMING_HISTORY_FILENAME_START)
    
    def read_audio_streaming_file(self, path: Path) -> pl.DataFrame:    
        df = pl.read_json(path)
        df = df.with_columns(
            pl.col('user_agent_decrypted').cast(pl.String),
            pl.col('episode_name').cast(pl.String),
            pl.col('episode_show_name').cast(pl.String),
            pl.col('spotify_episode_uri').cast(pl.String),
            )
        return df
    
    def load_data(self, path: Path) -> None:
        self.path = path
        
        file_paths = [filename for filename in os.listdir(path) if self.is_audio_streaming_history_file(path, filename)]
        dataframes = [self.read_audio_streaming_file(path / filename) for filename in file_paths]
        
        self.full_data = pl.concat(dataframes)
        
    def get_data(self) -> pl.DataFrame:
        group_by_expression = self.group_by_aggregate_parser.get_group_by_expression()
        aggregate_expression = self.group_by_aggregate_parser.get_aggregate_expression()
        
        if group_by_expression is None or aggregate_expression is None:
            print("Group by or aggregate function not set")
            return self.full_data
        
        print(f"Group by: {group_by_expression}, aggregate by: {aggregate_expression}")
        return self.full_data\
                .group_by(self.group_by_aggregate_parser.get_group_by_expression())\
                .agg(self.group_by_aggregate_parser.get_aggregate_expression())#\
                # .sort(pl.col(sort_by))
        