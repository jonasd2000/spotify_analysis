from abc import ABC, abstractmethod
from typing import Sequence

from sqlalchemy import select, insert
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlalchemy.ext.asyncio import AsyncSession

from .listening_event import ListeningEventSchema, MediaType, SpotifyListeningEventSchema
from .models import (
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
    async def get_media(self, session: AsyncSession, media_type: MediaType, listening_event_schemas: Sequence[SpotifyListeningEventSchema]) -> dict[SpotifyListeningEventSchema, Track | PodcastEpisode | AudiobookChapter]:
        match media_type:
            case MediaType.MUSIC_TRACK:
                stmt = (
                    select(SpotifyTrackData)
                    .options(selectinload(SpotifyTrackData.track))
                    .where(SpotifyTrackData.spotify_track_id.in_([schema.spotify_track_id for schema in listening_event_schemas]))
                )
                result = await session.execute(stmt)
                spotify_track_data = result.scalars().all()
                spotify_track_map = {data.spotify_track_id: data.track for data in spotify_track_data}
                return {
                    schema: spotify_track_map.get(schema.spotify_track_id)
                    for schema in listening_event_schemas
                }
            case MediaType.PODCAST_EPISODE:
                stmt = (
                    select(SpotifyPodcastEpisodeData)
                    .options(selectinload(SpotifyPodcastEpisodeData.episode))
                    .where(SpotifyPodcastEpisodeData.spotify_episode_id.in_([schema.spotify_track_id for schema in listening_event_schemas]))
                )
                result = await session.execute(stmt)
                spotify_podcast_episode_data = result.scalars().all()
                spotify_podcast_episode_map = {data.spotify_episode_id: data.episode for data in spotify_podcast_episode_data}
                return {
                    schema: spotify_podcast_episode_map.get(schema.spotify_track_id)
                    for schema in listening_event_schemas
                }
            case MediaType.AUDIOBOOK_CHAPTER:
                stmt = (
                    select(SpotifyAudiobookChapterData)
                    .options(selectinload(SpotifyAudiobookChapterData.chapter))
                    .where(SpotifyAudiobookChapterData.spotify_chapter_id.in_([schema.spotify_track_id for schema in listening_event_schemas]))
                )
                result = await session.execute(stmt)
                spotify_audiobook_chapter_data = result.scalars().all()
                spotify_audiobook_chapter_map = {data.spotify_chapter_id: data.chapter for data in spotify_audiobook_chapter_data}
                return {
                    schema: spotify_audiobook_chapter_map.get(schema.spotify_track_id)
                    for schema in listening_event_schemas
                }
            case _:
                raise ValueError(f"Unknown track type: {track_type}")
    
    async def get_or_create_artists(self, session: AsyncSession, artist_names: Sequence[str]) -> dict[str, Artist]:
        # returning a dict from name to model works because artist names are unique in our schema
        
        # GET ARTISTS FROM DB
        statement = (
            select(Artist)
            .where(Artist.artist_name.in_(artist_names))
        )
        result = await session.execute(statement)
        artists_in_db = result.scalars().all()
        artist_map = {artist.artist_name: artist for artist in artists_in_db}
        
        # CREATE ARTISTS NOT IN DB
        for artist_name in artist_names:
            if artist_name not in artist_map:
                new_artist = Artist(artist_name=artist_name)
                session.add(new_artist)
                artist_map[artist_name] = new_artist
                
        return artist_map
            
    async def get_or_create_albums(self, session: AsyncSession, album_names: Sequence[str]) -> dict[str, Album]:
        # returning a dict from name to model works because album names are unique in our schema
        
        # GET ALBUMS FROM DB
        statement = (
            select(Album)
            .where(Album.album_name.in_(album_names))
        )
        result = await session.execute(statement)
        albums_in_db = result.scalars().all()
        album_map = {album.album_name: album for album in albums_in_db}
        
        # CREATE ALBUMS NOT IN DB
        for album_name in album_names:
            if album_name not in album_map:
                new_album = Album(album_name=album_name)
                session.add(new_album)
                album_map[album_name] = new_album
                
        return album_map
            
    async def create_tracks(self, session: AsyncSession, listening_event_schemas: Sequence[SpotifyListeningEventSchema]) -> dict[SpotifyListeningEventSchema, Track]:
        artist_map = await self.get_or_create_artists(
            session,
            [artist_name for listening_event_schema in listening_event_schemas for artist_name in listening_event_schema.creators]
        )
        album_map = await self.get_or_create_albums(
            session,
            [listening_event_schema.collection_name for listening_event_schema in listening_event_schemas]
        )
        
        spotify_track_id_cache = {}
        schema_track_map = {}
        for listening_event_schema in listening_event_schemas:
            # using the cache like this leads to listening events with the same spotify_track_id to only be processed once
            key = listening_event_schema.spotify_track_id
            if key in spotify_track_id_cache:
                track = spotify_track_id_cache[key]
                schema_track_map[listening_event_schema] = track
                continue
            
            artists = [
                artist_map.get(artist_name)
                for artist_name in listening_event_schema.creators
            ]
            album = album_map.get(listening_event_schema.collection_name)
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
            
        return schema_track_map

    async def get_or_create_podcasts(self, session: AsyncSession, podcast_names: Sequence[str]) -> dict[str, Podcast]:
        # returning a dict from name to model works because podcast names are unique in our schema
        
        # GET PODCASTS FROM DB
        statement = (
            select(Podcast)
            .where(Podcast.podcast_name.in_(podcast_names))
        )
        result = await session.execute(statement)
        podcasts_in_db = result.scalars().all()
        podcast_map = {podcast.podcast_name: podcast for podcast in podcasts_in_db}
        
        # CREATE PODCASTS NOT IN DB
        for podcast_name in podcast_names:
            if podcast_name not in podcast_map:
                new_podcast = Podcast(podcast_name=podcast_name)
                session.add(new_podcast)
                podcast_map[podcast_name] = new_podcast
                
        return podcast_map

    async def create_podcast_episodes(self, session: AsyncSession, listening_event_schemas: Sequence[SpotifyListeningEventSchema]):
        podcast_map = await self.get_or_create_podcasts(
            session,
            [listening_event_schema.collection_name for listening_event_schema in listening_event_schemas]
        )
        
        spotify_episode_id_cache = {}
        schema_episode_map = {}
        for listening_event_schema in listening_event_schemas:
            # using the cache like this leads to listening events with the same spotify_track_id to only be processed once
            key = listening_event_schema.spotify_track_id
            if key in spotify_episode_id_cache:
                episode = spotify_episode_id_cache[key]
                schema_episode_map[listening_event_schema] = episode
                continue
            
            podcast = podcast_map.get(listening_event_schema.collection_name)
            episode = PodcastEpisode(
                episode_name=listening_event_schema.track_name,
                spotify_podcast_episode_data=SpotifyPodcastEpisodeData(
                    spotify_episode_id=listening_event_schema.spotify_track_id
                ),
                podcast=podcast,
            )
            
            session.add(episode)
            spotify_episode_id_cache[key] = episode
            schema_episode_map[listening_event_schema] = episode
            
        return schema_episode_map

    async def get_or_create_audiobooks(self, session: AsyncSession, audiobook_titles: Sequence[str]) -> dict[str, Audiobook]:
        # returning a dict from name to model works because audiobook names are unique in our schema
        
        # GET AUDIOBOOKS FROM DB
        statement = (
            select(Audiobook)
            .where(Audiobook.audiobook_title.in_(audiobook_titles))
        )
        result = await session.execute(statement)
        audiobooks_in_db = result.scalars().all()
        audiobook_map = {audiobook.audiobook_title: audiobook for audiobook in audiobooks_in_db}
        
        # CREATE AUDIOBOOKS NOT IN DB
        for audiobook_title in audiobook_titles:
            if audiobook_title not in audiobook_map:
                new_audiobook = Audiobook(audiobook_title=audiobook_title)
                session.add(new_audiobook)
                audiobook_map[audiobook_title] = new_audiobook
                
        return audiobook_map

    async def create_audiobook_chapters(self, session: AsyncSession, listening_event_schemas: Sequence[SpotifyListeningEventSchema]):
        audiobook_map = await self.get_or_create_audiobooks(
            session,
            [listening_event_schema.collection_name for listening_event_schema in listening_event_schemas]
        )
        
        spotify_chapter_id_cache = {}
        schema_chapter_map = {}
        for listening_event_schema in listening_event_schemas:
            # using the cache like this leads to listening events with the same spotify_track_id to only be processed once
            key = listening_event_schema.spotify_track_id
            if key in spotify_chapter_id_cache:
                chapter = spotify_chapter_id_cache[key]
                schema_chapter_map[listening_event_schema] = chapter
                continue
            
            audiobook = audiobook_map.get(listening_event_schema.collection_name)
            chapter = AudiobookChapter(
                chapter_title=listening_event_schema.track_name,
                spotify_audiobook_chapter_data=SpotifyAudiobookChapterData(
                    spotify_chapter_id=listening_event_schema.spotify_track_id
                ),
                audiobook=audiobook,
            )
            
            session.add(chapter)
            spotify_chapter_id_cache[key] = chapter
            schema_chapter_map[listening_event_schema] = chapter
            
        return schema_chapter_map

    async def _get_or_create_media(self, session: AsyncSession, media_type: MediaType, schemas_of_media_type: Sequence[SpotifyListeningEventSchema]):
        """Encapsulates the logic of finding or creating the media object."""
        creator = {
            MediaType.MUSIC_TRACK: self.create_tracks,
            MediaType.PODCAST_EPISODE: self.create_podcast_episodes,
            MediaType.AUDIOBOOK_CHAPTER: self.create_audiobook_chapters,
        }.get(media_type)
        if not creator:
            raise ValueError(f"Unsupported media type: {media_type}")
        
        
        # GETTING MEDIA
        schema_media = {}
        schema_media.update(await self.get_media(session, media_type, schemas_of_media_type))

        # now all schemas of which we found the spotify_track_id in the database, are keys in the schema_media dict
        # all those that were not found in the DB are not in the dict
        schemas_not_in_db = [s for s in schemas_of_media_type if schema_media.get(s) is None]

        # CREATING MEDIA
        # Dispatch to the appropriate creator based on type
        
        created_schema_track_map = await creator(session, schemas_not_in_db)
        schema_media.update(created_schema_track_map)
            
        return schema_media
    
    async def insert_listening_events(self, session: AsyncSession, schemas: Sequence[SpotifyListeningEventSchema]) -> None:
        SQLITE_PARAMETER_LIMIT = 32766
        MAX_PARAMETERS = 4  # in insert_batch, listening_event_data has the most parameters (4) that are inserted at once
        BATCH_SIZE = SQLITE_PARAMETER_LIMIT // MAX_PARAMETERS
        for i in range(0, len(schemas), BATCH_SIZE):
            batch = schemas[i:i + BATCH_SIZE]
            await self._insert_batch(session, batch)
        
    async def _insert_batch(self, session: AsyncSession, schemas: Sequence[SpotifyListeningEventSchema]) -> None:
        media_types_in_data = set(schema.media_type for schema in schemas)
        
        for media_type in media_types_in_data:
            # 1. Resolve Media (Still ORM-centric)
            schemas_of_media_type = [schema for schema in schemas if schema.media_type == media_type]

            schemas_with_media = await self._get_or_create_media(session, media_type, schemas_of_media_type)
            await session.flush() # flush to get media ids
            
            # 2. Prepare ListeningEvent UPSERT
            # the database column name of listening_event for the media type
            media_id_col = {
                MediaType.MUSIC_TRACK: "track_id",
                MediaType.PODCAST_EPISODE: "podcast_episode_id",
                MediaType.AUDIOBOOK_CHAPTER: "audiobook_chapter_id",
            }.get(media_type)
            # the model attribute containing its primary key
            model_primary_key_attr = {
                MediaType.MUSIC_TRACK: "track_id",
                MediaType.PODCAST_EPISODE: "episode_id",
                MediaType.AUDIOBOOK_CHAPTER: "chapter_id",
            }.get(media_type)
            
            event_values = []
            schema_key_map = {}
            for schema, media in schemas_with_media.items():
                media_pk = getattr(media, model_primary_key_attr)
                event_values.append({
                    "timestamp": schema.timestamp,
                    "milliseconds_played": schema.ms_played,
                    media_id_col: media_pk,
                })
                schema_key_map[(schema.timestamp, schema.ms_played, media_pk)] = schema

            # 3. Use an Atomic UPSERT (Industry Standard for high-volume)
            # This is ONE database round-trip. 
            event_stmt = (
                sqlite_upsert(ListeningEvent)
                .values(event_values)
                .on_conflict_do_nothing()
                .returning(
                    ListeningEvent.listening_event_id,
                    ListeningEvent.timestamp, ListeningEvent.milliseconds_played,
                    getattr(ListeningEvent, media_id_col),
                ) # Get the ID if inserted
            )

            result = await session.execute(event_stmt)
            inserted_ids = result.fetchall() # list of (id, timestamp, ms) tuples

            # 4. Prepare ListeningEventData UPSERT
            data_values = []
            for (event_id, event_timestamp, event_ms, media_id) in inserted_ids:
                schema = schema_key_map.get((event_timestamp, event_ms, media_id))
                if schema is None:
                    continue
                data_values.append({
                    "listening_event_id": event_id,
                    "reason_start": schema.reason_start,
                    "reason_end": schema.reason_end,
                    "shuffle": schema.shuffle
                })
            data_stmt = sqlite_upsert(ListeningEventData).values(data_values)
            await session.execute(data_stmt)