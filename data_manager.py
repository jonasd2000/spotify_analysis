import datetime
import io
from multiprocessing import Queue
from pathlib import Path
from typing import Set

import polars as pl
import spotipy

from data_labels import SPOTIFY_LABELS, DataLabels, fill_template

SPOTIFY_FILE_SCHEMA_TEMPLATE = {
    DataLabels.TIMESTAMP: pl.String,
    DataLabels.PLATFORM: pl.String,
    DataLabels.DURATION: pl.UInt32,
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


class DataManager:
    streaming_data: pl.DataFrame
    files_loaded: Set[str]
    audio_features: pl.DataFrame

    def __init__(self) -> None:
        self.streaming_data = pl.DataFrame()
        self.files_loaded = set()
        self.audio_features = pl.DataFrame()

    @staticmethod
    def read_audio_streaming_file(json_file: str | Path) -> pl.DataFrame:
        df = pl.read_json(
            json_file,
            schema=fill_template(SPOTIFY_FILE_SCHEMA_TEMPLATE, SPOTIFY_LABELS),
        )
        df = df.with_columns(  # fix datatypes
            pl.col("ts").str.to_datetime("%Y-%m-%dT%H:%M:%SZ"),
        )
        df = df.with_columns(
            pl.when(pl.col("spotify_track_uri").is_not_null())
            .then(pl.lit("track"))
            .when(pl.col("spotify_episode_uri").is_not_null())
            .then(pl.lit("episode"))
            .otherwise(pl.lit("unknown"))
            .alias("media_type"),
        )

        return df

    def append_files(self, file_names, file_contents) -> int:
        files_succesfully_loaded = set()
        for file_name, file_content in zip(file_names, file_contents):
            if file_name in self.files_loaded:
                continue
            new_data = self.read_audio_streaming_file(file_content.read())
            self.streaming_data = pl.concat((self.streaming_data, new_data))
            files_succesfully_loaded.add(file_name)

        self.files_loaded |= files_succesfully_loaded
        return len(files_succesfully_loaded)

    # def get_unique_track_ids(self) -> pl.Series:
    #     track_uris = self.streaming_data.drop_nulls("spotify_track_uri").select(pl.col("spotify_track_uri")).to_series()
    #     track_ids = track_uris.str.extract(r"spotify:track:(\w+)").alias("track_id")
    #     return track_ids.unique()

    def get_audio_features_from_file(self, track_data_file) -> pl.DataFrame:
        self.audio_features = pl.read_json(track_data_file.content.read())
        return self.audio_features

    def get_audio_features_from_spotify(
        self, queue: Queue, spotify_client_id: str, spotify_client_secret: str
    ) -> pl.DataFrame:
        spotipy_client = spotipy.Spotify(
            client_credentials_manager=spotipy.oauth2.SpotifyClientCredentials(
                client_id=spotify_client_id, client_secret=spotify_client_secret
            )
        )
        unique_track_uris = (
            self.streaming_data.select(pl.col("spotify_track_uri"))
            .to_series()
            .drop_nulls()
            .unique()
        )
        audio_features_list = []

        for i in range(0, len(unique_track_uris), 100):
            try:
                new_audio_features_list = spotipy_client.audio_features(
                    tracks=unique_track_uris[i : i + 100].to_list()
                )
                audio_features_list.extend(new_audio_features_list)
            except spotipy.exceptions.SpotifyException as e:
                print(f"Failed to get audio features\n{e}")
                continue

            queue.put_nowait(round(100 * i / len(unique_track_uris)))

        if audio_features_list:
            self.audio_features_df = pl.from_dicts(
                list(filter(lambda x: x is not None, audio_features_list))
            )

        return self.audio_features_df

    def get_min_max_date(self) -> tuple[datetime.datetime, datetime.datetime]:
        if self.streaming_data.is_empty():
            return None, None
        min_date = self.streaming_data.select(pl.col("ts").min()).to_series()[0]
        max_date = self.streaming_data.select(pl.col("ts").max()).to_series()[0]
        return min_date, max_date

    def audio_features_as_bytes(self) -> bytes:
        byte_buffer = io.BytesIO()
        self.audio_features.write_json(byte_buffer)
        return byte_buffer.getvalue()
