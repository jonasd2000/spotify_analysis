from dataclasses import dataclass
import datetime
import io

import pyinstrument

from nicegui import binding

from sqlalchemy import select, func as sql_func, Select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncEngine

from data.listening_event import MediaType
from data.models import (
    Base, 
    Track, Artist, Podcast,
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
class DateRangeFilteredStatistics:
    total_music_playtime: datetime.timedelta = datetime.timedelta(0)
    top_cache: dict[type[Base], list[tuple[Base, int]]] = None
    
    def set_top_items(self, media_type_model: type[Base], items: list[tuple[Base, int]]) -> None:
        if self.top_cache is None:
            self.top_cache = {}
        self.top_cache[media_type_model] = items

class DataManager:
    async_engine: AsyncEngine
    async_session: type[AsyncSession]
    
    static_data_metadata: StaticDataMetadata
    date_range_filtered_statistics: DateRangeFilteredStatistics

    def __init__(self) -> None:
        self.async_engine = create_async_engine("sqlite+aiosqlite:///listening_history.db")
        self.async_session = async_sessionmaker(self.async_engine, expire_on_commit=False)
        
        self.static_data_metadata = StaticDataMetadata()
        self.date_range_filtered_statistics = DateRangeFilteredStatistics()

    def _build_get_top_tracks_stmt(self, by=None, limit: int=10, filters: list|None=None) -> Select[tuple[Track, int]]:
        if by is None:
            by = sql_func.sum(ListeningEvent.milliseconds_played).desc()
        if filters is None:
            filters = []
        
        stmt = (
            select(Track, by.label("by_value"))
            .options(selectinload(Track.artists))
            .filter(*filters)
            .join(ListeningEvent, Track.track_id == ListeningEvent.track_id)
            .group_by(Track.track_id)
            .order_by(by.desc())
            .limit(limit)
        )
        
        return stmt

    def _build_get_top_artists_stmt(self, by=None, limit: int=10, filters: list|None=None) -> Select[tuple[Artist, int]]:
        if by is None:
            by = sql_func.sum(ListeningEvent.milliseconds_played).desc()
        if filters is None:
            filters = []
        
        stmt = (
            select(Artist, by.label("by_value"))
            .filter(*filters)
            # artists have to be joined to track through "track_artists" association table
            .join(Track, Track.track_id == ListeningEvent.track_id)
            .join(track_artist, Track.track_id == track_artist.c.track_id)
            .join(Artist, Artist.artist_id == track_artist.c.artist_id)
            .group_by(Artist.artist_id)
            .order_by(by.desc())
            .limit(limit)
        )
        
        return stmt

    def _build_get_top_podcasts_stmt(self, by=None, limit: int=10, filters: list|None=None) -> Select[tuple[Podcast, int]]:
        if by is None:
            by = sql_func.sum(ListeningEvent.milliseconds_played).desc()
        if filters is None:
            filters = []

        stmt = (
            select(Podcast, by.label("by_value"))
            .filter(*filters)
            .join(ListeningEvent, Podcast.podcast_id == ListeningEvent.podcast_episode_id)
            .group_by(Podcast.podcast_id)
            .order_by(by.desc())
            .limit(limit)
        )
        
        return stmt
        
    async def setup(self) -> None:
        await self.init_db()
        await self.refresh_metadata()
        await self.refresh_date_range_filtered_statistics()
        
    async def init_db(self) -> None:
        async with self.async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def refresh_metadata(self) -> None:
        await self._get_data_date_range()
        await self._get_has_listening_history_data()

    async def refresh_date_range_filtered_statistics(self, date_range: DateRange|None=None) -> None:
        date_range = date_range or self.static_data_metadata.data_date_range
        if date_range is None:
            return
        
        self.date_range_filtered_statistics.total_music_playtime = await self.get_total_play_time(MediaType.MUSIC_TRACK, date_range)
        
        playtime = sql_func.sum(ListeningEvent.milliseconds_played)
        date_range_filter = ListeningEvent.timestamp.between(date_range.start, date_range.end)
        top_tracks_stmt = self._build_get_top_tracks_stmt(by=playtime, limit=10, filters=[date_range_filter])
        top_artists_stmt = self._build_get_top_artists_stmt(by=playtime, limit=10, filters=[date_range_filter])
        top_podcasts_stmt = self._build_get_top_podcasts_stmt(by=playtime, limit=10, filters=[date_range_filter])

        for media_type_model, stmt in [
            (Track, top_tracks_stmt),
            (Artist, top_artists_stmt),
            (Podcast, top_podcasts_stmt)
        ]:
            async with self.async_session() as session:
                result = await session.execute(stmt)
                items = list(reversed(result.all()))
                self.date_range_filtered_statistics.set_top_items(media_type_model, items)

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
            await self.refresh_date_range_filtered_statistics()

    async def get_total_play_time(self, media_type: MediaType, date_range: DateRange = None) -> datetime.timedelta:
        date_range = date_range or self.static_data_metadata.data_date_range
        if date_range is None:
            return datetime.timedelta()
            
        async with self.async_session() as session:
            stmt = (
                select(sql_func.sum(ListeningEvent.milliseconds_played))
                .filter(ListeningEvent.timestamp.between(date_range.start, date_range.end))
                .select_from(ListeningEvent)
            )
            match media_type:
                case MediaType.MUSIC_TRACK:
                    stmt = stmt.where(ListeningEvent.track_id != None)
                case MediaType.PODCAST_EPISODE:
                    stmt = stmt.where(ListeningEvent.podcast_episode_id != None)
                case MediaType.AUDIOBOOK_CHAPTER:
                    stmt = stmt.where(ListeningEvent.audiobook_chapter_id != None)
            result = await session.execute(stmt)
            total_ms_played = result.scalar()
            return datetime.timedelta(milliseconds=total_ms_played) if total_ms_played is not None else datetime.timedelta()

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

    async def _get_total_music_playtime(self, date_range: DateRange = None) -> None:
        self.static_data_metadata.total_music_playtime = await self.get_total_play_time(MediaType.MUSIC_TRACK, date_range)
        
    def get_top[T: (Track, )](self, media_type_model: type[T], limit: int = 10) -> list[tuple[T, int]]:
        if self.date_range_filtered_statistics.top_cache is None:
            return []
        items = self.date_range_filtered_statistics.top_cache.get(media_type_model, [])
        return items[:limit]