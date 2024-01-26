from pathlib import Path
import os

import polars as pl

AUDIO_STREAMING_HISTORY_FILENAME_START = 'Streaming_History_Audio'

class DataManager:
    path: Path
    full_data: pl.DataFrame
    
    def __init__(self) -> None:
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
        