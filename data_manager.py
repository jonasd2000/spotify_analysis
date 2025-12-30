import datetime
import io
from multiprocessing import Queue
from pathlib import Path
from typing import List, Set

import polars as pl
import spotipy
from sqlalchemy import create_engine, Engine as SQLAlchemyEngine, select, func
from sqlalchemy.orm import Session

from data_labels import (
    SPOTIFY_LABELS,
    DataLabels,
    fill_template,
    map_labels_to_standard,
)
from data.models import Base, ListeningEvent
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
    engine: SQLAlchemyEngine

    def __init__(self) -> None:
        self.engine = create_engine("sqlite:///listening_history.db")
        Base.metadata.create_all(self.engine)

    def has_listening_history_data(self) -> bool:
        with Session(self.engine) as session:
            return session.execute(select(func.count()).select_from(ListeningEvent)).scalar() > 0

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

    def get_audio_features_from_file(self, track_data_file) -> pl.DataFrame:
        self.audio_features = pl.read_json(track_data_file.content.read())
        return self.audio_features

    def get_min_max_date(self) -> tuple[datetime.datetime, datetime.datetime]:
        """
        Retrieves the minimum and maximum timestamps from the streaming data.

        Returns
        -------
        tuple[datetime.datetime, datetime.datetime]
            A tuple containing the minimum and maximum dates. If the streaming
            data is empty, returns (None, None).
        """

        with Session(self.engine) as session:
            min_date = session.query(func.min(ListeningEvent.timestamp)).scalar()
            max_date = session.query(func.max(ListeningEvent.timestamp)).scalar()
            return min_date, max_date

    def audio_features_as_bytes(self) -> bytes:
        byte_buffer = io.BytesIO()
        self.audio_features.write_json(byte_buffer)
        return byte_buffer.getvalue()
