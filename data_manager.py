from dataclasses import dataclass
import datetime
import io

import pyinstrument

from nicegui import binding

from sqlalchemy import BinaryExpression, select, func as sql_func, Select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncEngine

from data.listening_event import MediaType
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
class DateRangeFilteredStatistics:
    total_playtime_cache: dict[type[Base], datetime.timedelta] = None
    top_cache: dict[type[Base], list[tuple[Base, int]]] = None
    unique_cache: dict[type[Base], int] = None
    
    def set_total_playtime(self, media_type_model: type[Base], playtime: datetime.timedelta) -> None:
        if self.total_playtime_cache is None:
            self.total_playtime_cache = {}
        self.total_playtime_cache[media_type_model] = playtime
    
    def set_top_items(self, media_type_model: type[Base], items: list[tuple[Base, int]]) -> None:
        if self.top_cache is None:
            self.top_cache = {}
        self.top_cache[media_type_model] = items
        
    def set_unique_count(self, media_type_model: type[Base], count: int) -> None:
        if self.unique_cache is None:
            self.unique_cache = {}
        self.unique_cache[media_type_model] = count

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
    date_range_filtered_statistics: DateRangeFilteredStatistics
    over_time_statistics: OverTimeStatistics

    def __init__(self) -> None:
        self.async_engine = create_async_engine("sqlite+aiosqlite:///listening_history.db")
        self.async_session = async_sessionmaker(self.async_engine, expire_on_commit=False)
        
        self.static_data_metadata = StaticDataMetadata()
        self.date_range_filtered_statistics = DateRangeFilteredStatistics()
        self.over_time_statistics = OverTimeStatistics()

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
    
    def _build_get_unique_tracks_stmt(self, filters: list|None=None) -> Select[int]:
        if filters is None:
            filters = []
        
        stmt = (
            select(sql_func.count(sql_func.distinct(Track.track_id)))
            .join(ListeningEvent, Track.track_id == ListeningEvent.track_id)
            .filter(*filters)
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
    
    def _build_get_unique_artists_stmt(self, filters: list|None=None) -> Select[int]:
        if filters is None:
            filters = []
        
        stmt = (
            select(sql_func.count(sql_func.distinct(Artist.artist_id)))
            .select_from(ListeningEvent)
            # artists have to be joined to track through "track_artists" association table
            .join(Track, Track.track_id == ListeningEvent.track_id)
            .join(track_artist, Track.track_id == track_artist.c.track_id)
            .join(Artist, Artist.artist_id == track_artist.c.artist_id)
            .filter(*filters)
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
            .join(PodcastEpisode, Podcast.podcast_id == PodcastEpisode.podcast_id)
            .join(ListeningEvent, PodcastEpisode.episode_id == ListeningEvent.podcast_episode_id)
            .group_by(Podcast.podcast_id)
            .order_by(by.desc())
            .limit(limit)
        )
        
        return stmt
    
    def _build_get_unique_podcasts_stmt(self, filters: list|None=None) -> Select[int]:
        if filters is None:
            filters = []
        
        stmt = (
            select(sql_func.count(sql_func.distinct(Podcast.podcast_id)))
            .select_from(ListeningEvent)
            .join(PodcastEpisode, PodcastEpisode.episode_id == ListeningEvent.podcast_episode_id)
            .join(Podcast, Podcast.podcast_id == PodcastEpisode.podcast_id)
            .filter(*filters)
        )
        
        return stmt
        
    async def setup(self) -> None:
        await self.init_db()
        await self.refresh_metadata()
        await self.refresh_date_range_filtered_statistics()

    async def get_track_over_time_statistics(self, track_id: int) -> None:
        async with self.async_session() as session:
            stmt = (
                select(sql_func.strftime("%Y-%m", ListeningEvent.timestamp), sql_func.sum(ListeningEvent.milliseconds_played))
                .filter(ListeningEvent.track_id == track_id)
                .group_by(sql_func.strftime("%Y-%m", ListeningEvent.timestamp))
                .order_by(ListeningEvent.timestamp)
            )
            result = await session.execute(stmt)
            over_time_data: dict[str, int] = {
                row[0]: row[1]
                for row in result.all()
            }
            self.over_time_statistics.set_track_over_time(track_id, over_time_data)

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

    async def _refresh_date_range_filtered_top_items(self, date_range_filter: BinaryExpression[bool]) -> None:
        playtime = sql_func.sum(ListeningEvent.milliseconds_played)
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

    async def _refresh_date_range_filtered_unique_counts(self, date_range_filter: BinaryExpression[bool]) -> None:
        unique_tracks_stmt = self._build_get_unique_tracks_stmt(filters=[date_range_filter])
        unique_artists_stmt = self._build_get_unique_artists_stmt(filters=[date_range_filter])
        unique_podcasts_stmt = self._build_get_unique_podcasts_stmt(filters=[date_range_filter])

        for media_type_model, stmt in [
            (Track, unique_tracks_stmt),
            (Artist, unique_artists_stmt),
            (Podcast, unique_podcasts_stmt)
        ]:
            async with self.async_session() as session:
                result = await session.execute(stmt)
                count = result.scalar_one()
                self.date_range_filtered_statistics.set_unique_count(media_type_model, count)
                
    async def refresh_date_range_filtered_statistics(self, date_range: DateRange|None=None) -> None:
        date_range = date_range or self.static_data_metadata.data_date_range
        if date_range is None:
            return
        
        # total music playtime
        self.date_range_filtered_statistics.set_total_playtime(MediaType.MUSIC_TRACK, await self.get_total_play_time(MediaType.MUSIC_TRACK, date_range))
        self.date_range_filtered_statistics.set_total_playtime(MediaType.PODCAST_EPISODE, await self.get_total_play_time(MediaType.PODCAST_EPISODE, date_range))
        self.date_range_filtered_statistics.set_total_playtime(MediaType.AUDIOBOOK_CHAPTER, await self.get_total_play_time(MediaType.AUDIOBOOK_CHAPTER, date_range))

        date_range_filter = ListeningEvent.timestamp.between(date_range.start, date_range.end)
        
        await self._refresh_date_range_filtered_top_items(date_range_filter)
        await self._refresh_date_range_filtered_unique_counts(date_range_filter)

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


    def get_top[T: (Base)](self, media_type_model: type[T], limit: int = 10) -> list[tuple[T, int]]:
        if self.date_range_filtered_statistics.top_cache is None:
            return []
        items = self.date_range_filtered_statistics.top_cache.get(media_type_model, [])
        return items[:limit]
    
    def get_unique[T: (Base)](self, media_type_model: type[T]) -> int:
        if self.date_range_filtered_statistics.unique_cache is None:
            return 0
        count = self.date_range_filtered_statistics.unique_cache.get(media_type_model, 0)
        return count