from dataclasses import dataclass
import datetime
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
    
@dataclass
class OverTimeStatistics:
    track_over_time: dict[int, dict[str, int]] = None
    artist_over_time: dict[int, dict[str, int]] = None
    
    def set_track_over_time(self, track_id: int, over_time_data: dict[str, int]) -> None:
        if self.track_over_time is None:
            self.track_over_time = {}
        self.track_over_time[track_id] = over_time_data
        
    def set_artist_over_time(self, artist_id: int, over_time_data: dict[str, int]) -> None:
        if self.artist_over_time is None:
            self.artist_over_time = {}
        self.artist_over_time[artist_id] = over_time_data

class DataManager:
    async_engine: AsyncEngine
    async_session: type[AsyncSession]
    
    static_data_metadata: StaticDataMetadata
    over_time_statistics: OverTimeStatistics

    def __init__(self) -> None:
        self.async_engine = create_async_engine("sqlite+aiosqlite:///listening_history.db")
        self.async_session = async_sessionmaker(self.async_engine, expire_on_commit=False)
        
        self.static_data_metadata = StaticDataMetadata()
        self.over_time_statistics = OverTimeStatistics()
    
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

        return stmt
        
    async def setup(self) -> None:
        await self.init_db()
        await self.refresh_metadata()

    async def get_artist_over_time_statistics(self, artist_id: int, force_refresh: bool=False) -> None:
        if (
            self.over_time_statistics.artist_over_time is not None
            and artist_id in self.over_time_statistics.artist_over_time 
            and not force_refresh
        ):
            return
        
        async with self.async_session() as session:
            stmt = (
                select(sql_func.strftime("%Y-%m", ListeningEvent.timestamp), sql_func.sum(ListeningEvent.milliseconds_played))
                .join(Track, Track.track_id == ListeningEvent.track_id)
                .join(track_artist, Track.track_id == track_artist.c.track_id)
                .filter(track_artist.c.artist_id == artist_id)
                .group_by(sql_func.strftime("%Y-%m", ListeningEvent.timestamp))
                .order_by(ListeningEvent.timestamp)
            )
            result = await session.execute(stmt)
            over_time_data: dict[str, int] = {
                row[0]: row[1]
                for row in result.all()
            }
            self.over_time_statistics.set_artist_over_time(artist_id, over_time_data)

    async def init_db(self) -> None:
        async with self.async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
    async def _get_has_listening_history_data(self) -> bool:
        async with self.async_session() as session:
            stmt = select(sql_func.count()).select_from(ListeningEvent)
            result = await session.execute(stmt)
            listening_event_count = result.scalar()
            self.static_data_metadata.has_listening_history_data = listening_event_count > 0

    async def _get_data_date_range(self) -> None:
        """
        Retrieves the minimum and maximum timestamps from the streaming data.

        Returns
        -------
        tuple[datetime.datetime, datetime.datetime]
            A tuple containing the minimum and maximum dates. If the streaming
            data is empty, returns (None, None).
        """

        async with self.async_session() as session:
            stmt = select(sql_func.min(ListeningEvent.timestamp), sql_func.max(ListeningEvent.timestamp))
            result = await session.execute(stmt)
            min_date, max_date = result.fetchone()
            
            if min_date is None or max_date is None:
                self.static_data_metadata.data_date_range = None
                return
            
            self.static_data_metadata.data_date_range = DateRange(min_date, max_date)

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
        
        listening_event_schemas = [
            ServiceListeningEventClass(**listening_event_data)
            for listening_event_data in transformed_listening_history_df.iter_rows(named=True)
        ]
        async with self.async_session() as session:
            await loader.insert_listening_events(session, listening_event_schemas)
            await session.commit()
            
            await self.refresh_metadata()
