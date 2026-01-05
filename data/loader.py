from abc import ABC, abstractmethod
from typing import Sequence

from sqlalchemy import select, insert
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlalchemy.ext.asyncio import AsyncSession

from .listening_event import ListeningEventSchema, MediaType, SpotifyListeningEventSchema
from .models import (
    get_or_create,
    Track, SpotifyTrackData, Album, Artist,
    PodcastEpisode, SpotifyPodcastEpisodeData, Podcast,
    AudiobookChapter, SpotifyAudiobookChapterData, Audiobook,
    ListeningEvent, ListeningEventData,
)


class Loader(ABC):
    url: str
        
    @abstractmethod
    async def insert_listening_events(self, session: AsyncSession, listening_event_schemas: Sequence[ListeningEventSchema]) -> None:
        pass
    
class SpotifyLoader(Loader):
    async def get_media(self, session: AsyncSession, track_type: MediaType, spotify_track_id: str) -> Track | PodcastEpisode | AudiobookChapter | None:
        match track_type:
            case MediaType.MUSIC_TRACK:
                result = await session.execute(
                    select(SpotifyTrackData)
                    .options(selectinload(SpotifyTrackData.track))
                    .where(SpotifyTrackData.spotify_track_id == spotify_track_id)
                )
                spotify_track_data = result.scalars().one_or_none()
                if spotify_track_data is None:
                    return None
                return spotify_track_data.track
            case MediaType.PODCAST_EPISODE:
                result = await session.execute(
                    select(SpotifyPodcastEpisodeData)
                    .options(selectinload(SpotifyPodcastEpisodeData.episode))
                    .where(SpotifyPodcastEpisodeData.spotify_episode_id == spotify_track_id)
                )
                spotify_podcast_episode_data = result.scalars().one_or_none()
                if spotify_podcast_episode_data is None:
                    return None
                return spotify_podcast_episode_data.episode
            case MediaType.AUDIOBOOK_CHAPTER:
                result = await session.execute(
                    select(SpotifyAudiobookChapterData)
                    .options(selectinload(SpotifyAudiobookChapterData.chapter))
                    .where(SpotifyAudiobookChapterData.spotify_chapter_id == spotify_track_id)
                )
                spotify_audiobook_chapter_data = result.scalars().one_or_none()
                if spotify_audiobook_chapter_data is None:
                    return None
                return spotify_audiobook_chapter_data.chapter
            case _:
                raise ValueError(f"Unknown track type: {track_type}")
            
    async def create_tracks(self, session: AsyncSession, listening_event_schemas: Sequence[SpotifyListeningEventSchema]) -> dict[SpotifyListeningEventSchema, Track]:
        spotify_track_id_cache = {}
        schema_track_map = {}
        for listening_event_schema in listening_event_schemas:
            key = listening_event_schema.spotify_track_id
            if key in spotify_track_id_cache:
                track = spotify_track_id_cache[key]
                schema_track_map[listening_event_schema] = track
                continue
            
            artists = [
                (await get_or_create(session, Artist, artist_name=artist_name, commit=False))[0]
                for artist_name in listening_event_schema.creators
            ]
            album, _ = await get_or_create(session, Album, album_name=listening_event_schema.collection_name, commit=False)
            track = Track(
                track_name=listening_event_schema.track_name,
                spotify_track_data=SpotifyTrackData(
                    spotify_track_id=listening_event_schema.spotify_track_id
                ),
                artists=artists,
                albums=[album],
            )
            
            session.add(track)
            spotify_track_id_cache[key] = track
            schema_track_map[listening_event_schema] = track
            
        await session.flush()
        # await session.flush()  # Ensure IDs are generated
        return schema_track_map

    async def _get_or_create_media(self, session: AsyncSession, schemas: Sequence[SpotifyListeningEventSchema]):
        """Encapsulates the logic of finding or creating the media object."""
        
        # GETTING MEDIA
        track_id_cache: dict[tuple[MediaType, str], Track | PodcastEpisode | AudiobookChapter] = {}
        schema_media = {}
        for schema in schemas:
            key = (schema.media_type, schema.spotify_track_id)
            if key not in track_id_cache:
                # fetch from DB, is None if not in DB
                media = await self.get_media(session, schema.media_type, schema.spotify_track_id)
                track_id_cache[key] = media
            media = track_id_cache[key]
            # media is not None if it was found in DB, otherwise it is
            if media is not None:
                schema_media[schema] = media

        # now all schemas of which i have found the spotify_track_id in the database, are keys in the schema_media dict
        # all those that were not found in the DB are not in the dict
        schemas_not_in_db = [s for s in schemas if s not in schema_media]

        # CREATING MEDIA
        # Dispatch to the appropriate creator based on type
        creators = {
            MediaType.MUSIC_TRACK: self.create_tracks,
            MediaType.PODCAST_EPISODE: None, # self.create_podcast_episode,
            MediaType.AUDIOBOOK_CHAPTER: None, # self.create_audiobook_chapter,
        }
        
        media_types = set(schema.media_type for schema in schemas_not_in_db)
        
        for media_type in media_types:
            creator = creators.get(media_type)
            if not creator:
                raise ValueError(f"Unsupported media type: {media_type}")
                
            schemas_of_media_type = [s for s in schemas_not_in_db if s.media_type == media_type]
            created_schema_track_map = await creator(session, schemas_of_media_type)
            schema_media.update(created_schema_track_map)
            
        return schema_media
    
    # async def map_schemas_to_media(self, session: AsyncSession, schemas: Sequence[SpotifyListeningEventSchema]) -> dict[SpotifyListeningEventSchema, Track | PodcastEpisode | AudiobookChapter]:
    #     track_id_cache: dict[tuple[MediaType, str], Track | PodcastEpisode | AudiobookChapter] = {}
    #     media_map: dict[SpotifyListeningEventSchema, Track | PodcastEpisode | AudiobookChapter] = {}
    #     for schema in schemas:
    #         key = (schema.media_type, schema.spotify_track_id)
    #         if key not in track_id_cache:
    #             media = await self._get_or_create_media(session, schema)
    #             track_id_cache[key] = media
    #         media_map[schema] = track_id_cache[key]
    #     return media_map
    
    async def insert_listening_events(self, session: AsyncSession, schemas: Sequence[SpotifyListeningEventSchema]) -> None:
        SQLITE_PARAMETER_LIMIT = 32766
        MAX_PARAMETERS = 4  # timestamp, milliseconds_played, media_id
        BATCH_SIZE = SQLITE_PARAMETER_LIMIT // MAX_PARAMETERS
        for i in range(0, len(schemas), BATCH_SIZE):
            batch = schemas[i:i + BATCH_SIZE]
            await self._insert_batch(session, batch)
        
    async def _insert_batch(self, session: AsyncSession, schemas: Sequence[SpotifyListeningEventSchema]) -> None:
        # 1. Resolve Media (Still ORM-centric)

        schemas_with_media = await self._get_or_create_media(session, schemas)
        # await session.flush() # flush to get media ids

        event_values = []
        for schema, media in schemas_with_media.items():
            media_id_col = {
                MediaType.MUSIC_TRACK: "track_id",
                MediaType.PODCAST_EPISODE: "podcast_episode_id",
                MediaType.AUDIOBOOK_CHAPTER: "audiobook_chapter_id",
            }.get(schema.media_type)
            # 2. Map Media ID to the correct column
            media_id_attr = {
                MediaType.MUSIC_TRACK: "track_id",
                MediaType.PODCAST_EPISODE: "podcast_episode_id",
                MediaType.AUDIOBOOK_CHAPTER: "audiobook_chapter_id",
            }.get(schema.media_type)
            
            event_values.append({
                "timestamp": schema.timestamp,
                "milliseconds_played": schema.ms_played,
                media_id_col: getattr(media, media_id_attr)
            })

        # 3. Use an Atomic UPSERT (Industry Standard for high-volume)
        # This is ONE database round-trip. 
        event_stmt = (
            sqlite_upsert(ListeningEvent)
            .values(event_values)
            .on_conflict_do_nothing()
            .returning(ListeningEvent.listening_event_id) # Get the ID if inserted
        )

        result = await session.execute(event_stmt)
        inserted_ids = result.fetchall() # list of (id,) tuples

        # 4. Conditional Metadata Insert
        # Only insert metadata if result is not None (meaning a new row was created)
        data_values = []
        for (event_id, ), schema in zip(inserted_ids, schemas):
            data_values.append({
                "listening_event_id": event_id,
                "reason_start": schema.reason_start,
                "reason_end": schema.reason_end,
                "shuffle": schema.shuffle
            })
        data_stmt = sqlite_upsert(ListeningEventData).values(data_values)
        await session.execute(data_stmt)