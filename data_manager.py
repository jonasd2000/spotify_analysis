from dataclasses import dataclass
import datetime
import io

import pyinstrument
from typing import Callable

from nicegui import binding

from sqlalchemy import select, func, Select
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

@binding.bindable_dataclass
class DataMetadata:
    data_date_range: DateRange | None = None
    has_listening_history_data: bool = False
    total_music_playtime: datetime.timedelta = datetime.timedelta(0)

class DataManager:
    async_engine: AsyncEngine
    async_session: type[AsyncSession]
    
    data_metadata: DataMetadata
    _top_cache: dict[type[Base], list[tuple[type[Base], int]] ]
    _top_query_builders: dict[type[Base], Callable[[int], Select]]

    def __init__(self) -> None:
        self.async_engine = create_async_engine("sqlite+aiosqlite:///listening_history.db")
        self.async_session = async_sessionmaker(self.async_engine, expire_on_commit=False)
        
        self.data_metadata = DataMetadata()
        self._top_cache = {}
        self._top_query_builders = {}
        self.register_top_query_builder(Track, self._build_track_top_by_playtime_query)
        self.register_top_query_builder(Artist, self._build_artist_top_by_playtime_query)
        self.register_top_query_builder(Podcast, self._build_podcast_top_by_playtime_query)
        
    def register_top_query_builder(self, media_type_model: type[Base], query_builder: Callable[[int], Select]) -> None:
        self._top_query_builders[media_type_model] = query_builder

    def _build_track_top_by_playtime_query(self, limit: int) -> Select[tuple[Track, int]]:
        stmt = (
            select(Track, func.sum(ListeningEvent.milliseconds_played).label("play_time"))
            .options(selectinload(Track.artists))
            .join(ListeningEvent, Track.track_id == ListeningEvent.track_id)
            .group_by(Track.track_id)
            .order_by(func.sum(ListeningEvent.milliseconds_played).desc())
            .limit(limit)
        )
        return stmt

    def _build_artist_top_by_playtime_query(self, limit: int) -> Select[tuple[Artist, int]]:
        stmt = (
            select(Artist, func.sum(ListeningEvent.milliseconds_played).label("play_time"))
            # artists have to be joined to track through "track_artists" association table
            .join(Track, Track.track_id == ListeningEvent.track_id)
            .join(track_artist, Track.track_id == track_artist.c.track_id)
            .join(Artist, Artist.artist_id == track_artist.c.artist_id)
            .group_by(Artist.artist_id)
            .order_by(func.sum(ListeningEvent.milliseconds_played).desc())
            .limit(limit)
        )
        return stmt

    def _build_podcast_top_by_playtime_query(self, limit: int) -> Select[tuple[Podcast, int]]:
        stmt = (
            select(Podcast, func.sum(ListeningEvent.milliseconds_played).label("play_time"))
            .join(ListeningEvent, Podcast.podcast_id == ListeningEvent.podcast_episode_id)
            .group_by(Podcast.podcast_id)
            .order_by(func.sum(ListeningEvent.milliseconds_played).desc())
            .limit(limit)
        )
        return stmt

    async def setup(self) -> None:
        await self.init_db()
        await self.refresh_metadata()
        await self.refresh_top_stats()
        
    async def init_db(self) -> None:
        async with self.async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def refresh_metadata(self) -> None:
        await self._get_data_date_range()
        await self._get_has_listening_history_data()
        await self._get_total_music_playtime()

    async def refresh_top_stats(self, targets: dict[type[Base], int] | None = None) -> None:
        async with self.async_session() as session:
            for model, builder in self._top_query_builders.items():
                limit = targets.get(model, 10) if targets is not None else 10
                
                # builder should be a statement that returns list of (model instance, playtime)
                stmt = builder(limit)
                result = await session.execute(stmt)
                top_instances = list(reversed(result.all()))
                self._top_cache[model] = top_instances

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
            for listening_event_data in transformed_listening_history_df.iter_rows(named=True):
                listening_event = ServiceListeningEventClass(**listening_event_data)
                await loader.insert_listening_event(session, listening_event)
            await session.commit()
            
            await self.refresh_metadata()
            await self.refresh_top_stats()

    async def get_total_play_time(self, media_type: MediaType) -> datetime.timedelta:
        async with self.async_session() as session:
            stmt = select(func.sum(ListeningEvent.milliseconds_played)).select_from(ListeningEvent)
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
            stmt = select(func.count()).select_from(ListeningEvent)
            result = await session.execute(stmt)
            listening_event_count = result.scalar()
            self.data_metadata.has_listening_history_data = listening_event_count > 0

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
            
            self.data_metadata._data_date_range = DateRange(min_date, max_date)

    async def _get_total_music_playtime(self) -> None:
        self.data_metadata.total_music_playtime = await self.get_total_play_time(MediaType.MUSIC_TRACK)
        
    def get_top[T: (Track, )](self, media_type_model: type[T], limit: int = 10) -> list[tuple[T, int]]:
        items = self._top_cache.get(media_type_model, [])
        return items[:limit]