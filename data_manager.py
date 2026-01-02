from dataclasses import dataclass
import datetime
import io

import polars as pl
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncEngine

from data.models import Base, ListeningEvent
from data.services import recognise_listening_history_service, service_data_pipelines, ServiceNotFoundError

@dataclass
class DateRange:
    start: datetime.datetime
    end: datetime.datetime


class DataManager:
    engine: AsyncEngine
    async_session: type[AsyncSession]
    
    _data_date_range: DateRange | None
    _has_listening_history_data: bool

    @property
    def data_date_range(self) -> DateRange | None:
        return self._data_date_range
    
    @property
    def has_listening_history_data(self) -> bool:
        return self._has_listening_history_data

    def __init__(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///listening_history.db")
        self.async_session = async_sessionmaker(self.engine, expire_on_commit=False)
        
        self._data_date_range = None
        self._has_listening_history_data = False

    async def setup(self) -> None:
        await self.init_db()
        await self.refresh_metadata()
        
    async def init_db(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def refresh_metadata(self) -> None:
        await self._get_data_date_range()
        await self._get_has_listening_history_data()

    async def load_file_to_database(self, file_name: str, file_content: io.BytesIO) -> None:
        listening_history_service = recognise_listening_history_service(file_name)
        if listening_history_service is None:
            raise ServiceNotFoundError()
        
        data_pipeline = service_data_pipelines[listening_history_service]
        
        parser = data_pipeline.parser()
        transformer = data_pipeline.transformer()
        loader = data_pipeline.loader()
        
        listening_history_df = parser.parse_data(file_content)
        transformed_listening_history_df = transformer.transform_data(listening_history_df)
        
        ServiceListeningEventClass = data_pipeline.listening_event
        
        async with self.async_session() as session:
            for listening_event_data in transformed_listening_history_df.iter_rows(named=True):
                listening_event = ServiceListeningEventClass(**listening_event_data)
                await loader.insert_listening_event(session, listening_event)
            await session.commit()
            await self.refresh_metadata()

    def get_audio_features_from_file(self, track_data_file) -> pl.DataFrame:
        self.audio_features = pl.read_json(track_data_file.content.read())
        return self.audio_features

    async def _get_has_listening_history_data(self) -> bool:
        async with self.async_session() as session:
            stmt = select(func.count()).select_from(ListeningEvent)
            result = await session.execute(stmt)
            listening_event_count = result.scalar()
            self._has_listening_history_data = listening_event_count > 0

    async def _get_data_date_range(self) -> None:
        """
        Retrieves the minimum and maximum timestamps from the streaming data.

        Returns
        -------
        tuple[datetime.datetime, datetime.datetime]
            A tuple containing the minimum and maximum dates. If the streaming
            data is empty, returns (None, None).
        """

        # TODO: Figure out how to pass dates to widgets
        async with self.async_session() as session:
            stmt = select(func.min(ListeningEvent.timestamp), func.max(ListeningEvent.timestamp))
            result = await session.execute(stmt)
            min_date, max_date = result.fetchone()
            
            self._data_date_range = DateRange(min_date, max_date)
