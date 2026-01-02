from abc import ABC, abstractmethod

from sqlalchemy import select
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
    async def insert_listening_event(self, session: AsyncSession, listening_event_schema: ListeningEventSchema) -> None:
        pass
    
class SpotifyLoader(Loader):
    async def _get_or_create_media(self, session: AsyncSession, schema: SpotifyListeningEventSchema):
        """Encapsulates the logic of finding or creating the media object."""
        media = await self.get_media(session, schema.media_type, schema.spotify_track_id)
        if media:
            return media

        # Dispatch to the appropriate creator based on type
        creators = {
            MediaType.MUSIC_TRACK: self.create_track,
            MediaType.PODCAST_EPISODE: None, # self.create_podcast_episode,
            MediaType.AUDIOBOOK_CHAPTER: None, # self.create_audiobook_chapter,
        }
        
        creator = creators.get(schema.media_type)
        if not creator:
            raise ValueError(f"Unsupported media type: {schema.media_type}")
            
        return await creator(session, schema)
    
    async def create_track(self, session: AsyncSession, listening_event_schema: SpotifyListeningEventSchema):
        artists = [
            (await get_or_create(session, Artist, artist_name=artist_name))[0]
            for artist_name in listening_event_schema.creators
        ]
        album, _ = await get_or_create(session, Album, album_name=listening_event_schema.collection_name)
        track = Track(
            track_name=listening_event_schema.track_name,
            spotify_track_data=SpotifyTrackData(
                spotify_track_id=listening_event_schema.spotify_track_id
            ),
            artists=artists,
        )
        track.albums.append(album)
        
        session.add(track)
        
        return track
    
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
    
    async def insert_listening_event(self, session: AsyncSession, schema: SpotifyListeningEventSchema) -> None:
        # 1. Resolve Media (Still ORM-centric)
        media = await self._get_or_create_media(session, schema)
        await session.flush()  # We need the media ID

        # 2. Map Media ID to the correct column
        media_id_col = {
            MediaType.MUSIC_TRACK: "track_id",
            MediaType.PODCAST_EPISODE: "podcast_episode_id",
            MediaType.AUDIOBOOK_CHAPTER: "audiobook_chapter_id",
        }.get(schema.media_type)

        # 3. Use an Atomic UPSERT (Industry Standard for high-volume)
        # This is ONE database round-trip. 
        event_stmt = (
            sqlite_upsert(ListeningEvent)
            .values({
                "timestamp": schema.timestamp,
                "milliseconds_played": schema.ms_played,
                media_id_col: getattr(media, "track_id" if schema.media_type == MediaType.MUSIC_TRACK 
                                        else "episode_id" if schema.media_type == MediaType.PODCAST_EPISODE 
                                        else "chapter_id"
                )
            })
            .on_conflict_do_nothing()
            .returning(ListeningEvent.listening_event_id) # Get the ID if inserted
        )

        result = await session.execute(event_stmt)
        result = result.fetchone()

        # 4. Conditional Metadata Insert
        # Only insert metadata if result is not None (meaning a new row was created)
        if result:
            new_id = result[0]
            data_stmt = sqlite_upsert(ListeningEventData).values(
                listening_event_id=new_id,
                reason_start=schema.reason_start,
                reason_end=schema.reason_end,
                shuffle=schema.shuffle
            )
            await session.execute(data_stmt)