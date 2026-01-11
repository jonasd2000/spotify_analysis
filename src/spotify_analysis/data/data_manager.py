from dataclasses import dataclass
import datetime
import logging
import io

from nicegui import binding

from sqlalchemy import select, func as sql_func, Select, inspect
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncEngine

from data.models import (
    Base, 
    Track, Artist, Podcast, PodcastEpisode,
    ListeningEvent,
    track_artist
)
from data.services import recognise_listening_history_service, service_data_pipelines, ServiceNotFoundError


logger = logging.getLogger(__name__)

@dataclass
class DateRange:
    start: datetime.datetime
    end: datetime.datetime
    
    @property
    def days(self) -> int:
        return (self.end - self.start).days

@binding.bindable_dataclass
class StaticDataMetadata:
    data_date_range: DateRange | None = None
    has_listening_history_data: bool = False
    
class DataManager:
    async_engine: AsyncEngine
    async_session: type[AsyncSession]
    
    static_data_metadata: StaticDataMetadata

    def __init__(self) -> None:
        self.async_engine = create_async_engine("sqlite+aiosqlite:///listening_history.db")
        self.async_session = async_sessionmaker(self.async_engine, expire_on_commit=False)
        
        self.static_data_metadata = StaticDataMetadata()
    
    @staticmethod
    def _join_to_listening_event(stmt: Select, model: type[Base]):
        if model is Track:
            stmt = stmt.join(Track, Track.track_id == ListeningEvent.track_id)
            return stmt
        if model is Artist:
            stmt = stmt.join(Track, Track.track_id == ListeningEvent.track_id)
            stmt = stmt.join(track_artist, Track.track_id == track_artist.c.track_id)
            stmt = stmt.join(Artist, Artist.artist_id == track_artist.c.artist_id)
            return stmt
        if model is Podcast:
            stmt = stmt.join(Podcast, Podcast.podcast_id == PodcastEpisode.podcast_id)
            stmt = stmt.join(PodcastEpisode, PodcastEpisode.episode_id == ListeningEvent.podcast_episode_id)
            return stmt
        
        raise NotImplementedError(f"Model {model} is not supported.")
        
    @staticmethod
    def build_top_stmt[T: type[Base]](model: T, by=None, limit: int=10, filters: list|None=None, options: list|None=None) -> Select[tuple[T, int]]:
        if by is None:
            by = sql_func.sum(ListeningEvent.milliseconds_played).desc()
        if filters is None:
            filters = []
        if options is None:
            options = []
            
        insp = inspect(model)
        model_pk = insp.primary_key
        
        stmt = (
            select(model, by.label("by_value"))
            .options(*options)
        )
        
        stmt = DataManager._join_to_listening_event(stmt, model)
        
        stmt = (
            stmt
            .filter(*filters)
            .group_by(*model_pk)
            .order_by(by.desc())
            .limit(limit)
        )
        logger.debug(f"Built top statement for {model=}, {by=}, {limit=}, {filters=}, {options=}: {stmt}")
        
        return stmt
        
    @staticmethod
    def build_unique_stmt(model: type[Base], filters: list|None=None) -> Select[int]:
        if filters is None:
            filters = []
            
        insp = inspect(model)
        model_pk = insp.primary_key
        
        stmt = (
            select(sql_func.count(sql_func.distinct(*model_pk)))
            .select_from(ListeningEvent)
        )
        
        stmt = DataManager._join_to_listening_event(stmt, model)
        
        stmt = (
            stmt
            .filter(*filters)
        )
        logger.debug(f"Built unique statement for {model=}, {filters=}: {stmt}")

        return stmt
        
    async def setup(self) -> None:
        logger.debug("Setting up data manager...")
        await self.init_db()
        await self.refresh_metadata()

    async def init_db(self) -> None:
        logger.debug(f"Initializing database with url {self.async_engine.url}...")
        async with self.async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
    async def _get_has_listening_history_data(self) -> bool:
        logger.debug("Getting has listening history data...")
        async with self.async_session() as session:
            stmt = select(sql_func.count()).select_from(ListeningEvent)
            result = await session.execute(stmt)
            listening_event_count = result.scalar()
            
            has_listening_history_data = listening_event_count > 0
            logger.debug(f"Has listening history data: {has_listening_history_data}")
            self.static_data_metadata.has_listening_history_data = has_listening_history_data

    async def _get_data_date_range(self) -> None:
        """
        Retrieves the minimum and maximum timestamps from the streaming data.

        Returns
        -------
        tuple[datetime.datetime, datetime.datetime]
            A tuple containing the minimum and maximum dates. If the streaming
            data is empty, returns (None, None).
        """

        logger.debug("Getting data date range...")
        async with self.async_session() as session:
            stmt = select(sql_func.min(ListeningEvent.timestamp), sql_func.max(ListeningEvent.timestamp))
            result = await session.execute(stmt)
            min_date, max_date = result.fetchone()
            
            if min_date is None or max_date is None:
                logger.debug(f"Date range data incomplete: {min_date=}, {max_date=}")
                self.static_data_metadata.data_date_range = None
                return
            
            date_range = DateRange(min_date, max_date)
            logger.info(f"Set data date range: {date_range}")
            self.static_data_metadata.data_date_range = date_range

    async def refresh_metadata(self) -> None:
        logger.debug("Refreshing metadata...")
        await self._get_data_date_range()
        await self._get_has_listening_history_data()

    async def load_file_to_database(self, file_name: str, file_content: io.BytesIO) -> None:
        logger.info(f"Loading file {file_name} to database...")
        
        listening_history_service = recognise_listening_history_service(file_name)
        if listening_history_service is None:
            error = ServiceNotFoundError()
            logger.exception(error)
            raise error
        
        data_pipeline = service_data_pipelines[listening_history_service]
        
        parser = data_pipeline.parser()
        transformer = data_pipeline.transformer()
        loader = data_pipeline.loader()
        
        logger.debug(f"For Service {listening_history_service}, using {parser=}, {transformer=}, {loader=}")
        
        listening_history_df = parser.parse_data(file_content)
        transformed_listening_history_df = transformer.transform_data(listening_history_df)
        
        ServiceListeningEventClass = data_pipeline.listening_event
        
        listening_event_schemas = [
            ServiceListeningEventClass(**listening_event_data)
            for listening_event_data in transformed_listening_history_df.iter_rows(named=True)
        ]
        async with self.async_session() as session:
            await loader.insert_listening_events(session, listening_event_schemas)
            await session.commit()
            
        await self.refresh_metadata()
