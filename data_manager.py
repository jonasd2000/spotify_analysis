import datetime
import io
from multiprocessing import Queue
from pathlib import Path
from typing import List, Set

import polars as pl
import spotipy
from sqlalchemy import create_engine, Engine as SQLAlchemyEngine
from sqlalchemy.orm import Session

from data_labels import (
    SPOTIFY_LABELS,
    DataLabels,
    fill_template,
    map_labels_to_standard,
)
from data.models import Base
from data.services import recognise_listening_history_service, service_data_pipelines, ServiceNotFoundError

SPOTIFY_FILE_SCHEMA_TEMPLATE = {
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


class DataManager:
    """
    Manages the data from the audio streaming files.

    Attributes
    ----------
    streaming_data : pl.DataFrame
        The data from the audio streaming files.
    files_loaded : Set[str]
        The names of the files that have been loaded.
    audio_features : pl.DataFrame
        The audio features.
    """

    streaming_data: pl.DataFrame
    files_loaded: Set[str]
    audio_features: pl.DataFrame
    engine: SQLAlchemyEngine

    def __init__(self) -> None:
        self.streaming_data = pl.DataFrame()
        self.files_loaded = set()
        self.audio_features = pl.DataFrame()
        
        self.engine = create_engine("sqlite:///listening_history.db")
        Base.metadata.create_all(self.engine)

    @staticmethod
    def read_audio_streaming_file(json_file: str | Path) -> pl.DataFrame:
        """
        Reads an audio streaming file.

        This function reads an audio streaming file and returns a dataframe with the data from the file.
        Renames the columns to standard names.

        Parameters
        ----------
        json_file : str | Path
            The file to read.

        Returns
        -------
        pl.DataFrame
            The data from the file.
        """

        df = pl.read_json(
            json_file,
            schema=fill_template(SPOTIFY_FILE_SCHEMA_TEMPLATE, SPOTIFY_LABELS),
        ).rename(
            map_labels_to_standard(SPOTIFY_LABELS)
        )  # rename columns to standard names

        # fix datatypes
        df = df.with_columns(
            pl.col(DataLabels.TIMESTAMP.value).str.to_datetime("%Y-%m-%dT%H:%M:%SZ"),
        )

        # add media type
        df = df.with_columns(
            pl.when(pl.col(DataLabels.TRACK_ID.value).is_not_null())
            .then(pl.lit("track"))
            .when(pl.col(DataLabels.PODCAST_EPISODE_ID.value).is_not_null())
            .then(pl.lit("episode"))
            .otherwise(pl.lit("unknown"))
            .alias(DataLabels.MEDIA_TYPE.value),
        )

        return df

    @staticmethod
    def load_file_to_database(database_address: str, file_name: str, file_content: str) -> None:
        engine = create_engine(database_address)
        file_content_buffer = io.BytesIO(file_content)
        
        listening_history_service = recognise_listening_history_service(file_name)
        if listening_history_service is None:
            raise ServiceNotFoundError()
        
        data_pipeline = service_data_pipelines[listening_history_service]
        
        parser = data_pipeline.parser()
        transformer = data_pipeline.transformer()
        loader = data_pipeline.loader()
        
        listening_history_df = parser.parse_data(file_content_buffer)
        transformed_listening_history_df = transformer.transform_data(listening_history_df)
        
        ServiceListeningEventClass = data_pipeline.listening_event
        
        with Session(engine) as session:
            for listening_event_data in transformed_listening_history_df.iter_rows(named=True):
                listening_event = ServiceListeningEventClass(**listening_event_data)
                loader.insert_listening_event(session, listening_event)
            session.commit()

    def append_files(
        self, file_names: List[str], file_contents: List[io.BytesIO]
    ) -> int:
        """
        Appends the data from the given files to the streaming data.

        This function iterates over the given files and file contents.
        If a file name is already in the files_loaded set, it is skipped.
        Otherwise, the data from the file is read and appended to the streaming data.
        The files_succesfully_loaded set is updated with the new files.
        The function returns the number of files successfully loaded.

        Parameters
        ----------
        file_names : list[str]
            The names of the files to load.
        file_contents : list[io.BytesIO]
            The contents of the files to load.

        Returns
        -------
        int
            The number of files successfully loaded.
        """
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
    #     track_uris = self.streaming_data.drop_nulls(DataLabels.TRACK_ID.value).select(pl.col(DataLabels.TRACK_ID.value)).to_series()
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
            self.streaming_data.select(pl.col(DataLabels.TRACK_ID.value))
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
        """
        Retrieves the minimum and maximum timestamps from the streaming data.

        Returns
        -------
        tuple[datetime.datetime, datetime.datetime]
            A tuple containing the minimum and maximum dates. If the streaming
            data is empty, returns (None, None).
        """

        if self.streaming_data.is_empty():
            return None, None
        min_date = self.streaming_data.select(
            pl.col(DataLabels.TIMESTAMP.value).min()
        ).to_series()[0]
        max_date = self.streaming_data.select(
            pl.col(DataLabels.TIMESTAMP.value).max()
        ).to_series()[0]
        return min_date, max_date

    def audio_features_as_bytes(self) -> bytes:
        byte_buffer = io.BytesIO()
        self.audio_features.write_json(byte_buffer)
        return byte_buffer.getvalue()
