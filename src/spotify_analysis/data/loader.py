from abc import ABC, abstractmethod
import datetime
import logging
from typing import Sequence, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlalchemy.ext.asyncio import AsyncSession

from .listening_event import ListeningEventSchema, MediaType, SpotifyListeningEventSchema
from .models import (
    Track, SpotifyTrackData, 
    Artist, SpotifyArtistData,
    Album, SpotifyAlbumData,
    PodcastEpisode, SpotifyPodcastEpisodeData, Podcast,
    AudiobookChapter, SpotifyAudiobookChapterData, Audiobook,
    ListeningEvent, ListeningEventData,
)


logger = logging.getLogger(__name__)


class Loader(ABC):
    url: str
        
    @abstractmethod
    async def insert_listening_events(self, session: AsyncSession, listening_event_schemas: Sequence[ListeningEventSchema]) -> None:
        pass
    
class SpotifyLoader(Loader):
    async def get_media(self, session: AsyncSession, media_type: MediaType, listening_event_schemas: Sequence[SpotifyListeningEventSchema]) -> dict[SpotifyListeningEventSchema, Track | PodcastEpisode | AudiobookChapter]:
        logger.debug(f"Getting media for {media_type} for {len(listening_event_schemas)} listening events...")
        match media_type:
            case MediaType.MUSIC_TRACK:
                schema_media = {}
                tracks_by_isrc_statement = (
                    select(Track)
                    .where(Track.international_standard_recording_code.in_([schema.isrc for schema in listening_event_schemas if schema.isrc is not None]))
                )
                tracks_by_isrc_result = await session.execute(tracks_by_isrc_statement)
                tracks_by_isrc = tracks_by_isrc_result.scalars().all()
                isrc_track_map = {track.international_standard_recording_code: track for track in tracks_by_isrc}
                
                tracks_without_isrc_by_spotify_uri_statement = (
                    select(SpotifyTrackData)
                    .options(selectinload(SpotifyTrackData.track))
                    .join(Track, SpotifyTrackData.track_id == Track.track_id)
                    .where(Track.international_standard_recording_code.is_(None))
                    .where(SpotifyTrackData.spotify_uri.in_([schema.spotify_track_id for schema in listening_event_schemas if schema.isrc is None]))
                )
                tracks_without_isrc_by_spotify_uri_result = await session.execute(tracks_without_isrc_by_spotify_uri_statement)
                tracks_without_isrc_by_spotify_uri = tracks_without_isrc_by_spotify_uri_result.scalars().all()
                spotify_uri_track_map = {data.spotify_uri: data.track for data in tracks_without_isrc_by_spotify_uri}
                
                for schema in listening_event_schemas:
                    if schema.isrc is not None:
                        schema_media[schema] = isrc_track_map.get(schema.isrc)
                    else:
                        schema_media[schema] = spotify_uri_track_map.get(schema.spotify_track_id)
                
                return schema_media
            case MediaType.PODCAST_EPISODE:
                tracks_by_isrc_statement = (
                    select(SpotifyPodcastEpisodeData)
                    .options(selectinload(SpotifyPodcastEpisodeData.episode))
                    .where(SpotifyPodcastEpisodeData.spotify_episode_id.in_([schema.spotify_track_id for schema in listening_event_schemas]))
                )
                tracks_by_isrc_result = await session.execute(tracks_by_isrc_statement)
                spotify_podcast_episode_data = tracks_by_isrc_result.scalars().all()
                spotify_podcast_episode_map = {data.spotify_episode_id: data.episode for data in spotify_podcast_episode_data}
                return {
                    schema: spotify_podcast_episode_map.get(schema.spotify_track_id)
                    for schema in listening_event_schemas
                }
            case MediaType.AUDIOBOOK_CHAPTER:
                tracks_by_isrc_statement = (
                    select(SpotifyAudiobookChapterData)
                    .options(selectinload(SpotifyAudiobookChapterData.chapter))
                    .where(SpotifyAudiobookChapterData.spotify_chapter_id.in_([schema.spotify_track_id for schema in listening_event_schemas]))
                )
                tracks_by_isrc_result = await session.execute(tracks_by_isrc_statement)
                spotify_audiobook_chapter_data = tracks_by_isrc_result.scalars().all()
                spotify_audiobook_chapter_map = {data.spotify_chapter_id: data.chapter for data in spotify_audiobook_chapter_data}
                return {
                    schema: spotify_audiobook_chapter_map.get(schema.spotify_track_id)
                    for schema in listening_event_schemas
                }
            case _:
                raise ValueError(f"Unknown track type: {track_type}")
    
    async def get_or_create_artists(self, session: AsyncSession, artists: Sequence[dict[str, str]]) -> dict[str, Artist]:
        logger.debug(f"Getting or creating artists for {len(artists)} artists...")
        
        # GET ARTISTS FROM DB
        artist_uris = [artist["uri"] for artist in artists]
        statement = (
            select(Artist)
            .options(selectinload(Artist.spotify_artist_data))
            .join(SpotifyArtistData)
            .where(SpotifyArtistData.spotify_uri.in_(artist_uris))
        )
        result = await session.execute(statement)
        artists_in_db = result.scalars().all()
        artist_map = {artist.spotify_artist_data.spotify_uri: artist for artist in artists_in_db}
        logger.debug(f"Found {len(artists_in_db)} artists in DB...")
        
        # CREATE ARTISTS NOT IN DB
        for artist in artists:
            artist_uri = artist["uri"]
            if artist_uri not in artist_map:
                artist_name = artist["name"]
                new_artist = Artist(
                    artist_name=artist_name,
                    spotify_artist_data=SpotifyArtistData(spotify_uri=artist_uri)
                )
                artist_map[artist_uri] = new_artist
                session.add(new_artist)
        logger.debug(f"Created {len(artist_map) - len(artists_in_db)} new artists...")
                
        return artist_map
            
    def parse_date(self, date_str: str, precision: str) -> Optional[datetime.date]:
        pattern = "%Y-%m-%d"
        if precision == "year":
            pattern = "%Y"
        elif precision == "month":
            pattern = "%Y-%m"
        try:
            date = datetime.datetime.strptime(date_str, pattern).date()
        except ValueError:
            return None
            
        return date
    
    async def get_or_create_albums(self, session: AsyncSession, albums: Sequence[dict[str, str]]) -> dict[str, Album]:
        logger.debug(f"Getting or creating albums for {len(albums)} albums...")
        
        # GET ALBUMS FROM DB
        album_uris = [album["uri"] for album in albums]
        statement = (
            select(Album)
            .options(selectinload(Album.spotify_album_data))
            .join(SpotifyAlbumData)
            .where(SpotifyAlbumData.spotify_uri.in_(album_uris))
        )
        result = await session.execute(statement)
        albums_in_db = result.scalars().all()
        album_map = {album.spotify_album_data.spotify_uri: album for album in albums_in_db}
        logger.debug(f"Found {len(albums_in_db)} albums in DB...")
        
        # CREATE ALBUMS NOT IN DB
        for album in albums:
            album_uri = album["uri"]
            if album_uri not in album_map:
                album_name = album["name"]
                album_type = album["album_type"]
                total_tracks = album["total_tracks"]
                release_date = album["release_date"]
                release_date_precision = album["release_date_precision"]
                
                release_date = self.parse_date(release_date, release_date_precision)
                
                new_album = Album(
                    album_name=album_name,
                    album_type=album_type,
                    total_tracks=total_tracks,
                    release_date=release_date,
                    spotify_album_data=SpotifyAlbumData(
                        spotify_uri=album_uri,
                        release_date_precision=release_date_precision
                    )
                )
                album_map[album_uri] = new_album
                session.add(new_album)
        logger.debug(f"Created {len(album_map) - len(albums_in_db)} new albums...")
                
        return album_map
            
    async def create_tracks(self, session: AsyncSession, listening_event_schemas: Sequence[SpotifyListeningEventSchema]) -> dict[SpotifyListeningEventSchema, Track]:
        logger.debug(f"Creating {len(listening_event_schemas)} tracks...")
        artist_map = await self.get_or_create_artists(
            session,
            [
                artist
                for listening_event_schema in listening_event_schemas
                for artist in listening_event_schema.artists
            ]
        )
        album_map = await self.get_or_create_albums(
            session,
            [listening_event_schema.album for listening_event_schema in listening_event_schemas]
        )
        
        spotify_track_id_cache = {}
        schema_track_map = {}
        for listening_event_schema in listening_event_schemas:
            logger.debug(f"Creating track for schema: {listening_event_schema}")
            # using the cache like this leads to listening events with the same spotify_track_id to only be processed once
            key = listening_event_schema.isrc
            if key is None:
                logger.debug(f"Choosing spotify_uri as key: {listening_event_schema.spotify_track_id}")
                key = listening_event_schema.spotify_track_id
            else:
                logger.debug(f"Choosing isrc as key: {listening_event_schema.isrc}")
            
            if key in spotify_track_id_cache:
                logger.debug(f"Found track in current cache: {key}")
                track: Track = spotify_track_id_cache[key]
                track.add_spotify_track_data(SpotifyTrackData(
                    spotify_uri=listening_event_schema.spotify_track_id,
                    explicit=listening_event_schema.explicit
                ))
                schema_track_map[listening_event_schema] = track
                continue
            
            artists = [artist_map.get(artist["uri"]) for artist in listening_event_schema.artists]
            album = album_map.get(listening_event_schema.album["uri"])
            
            logger.debug(listening_event_schema.isrc, spotify_track_id_cache)
            
            track = Track(
                track_name=listening_event_schema.track_name,
                international_standard_recording_code=listening_event_schema.isrc,
                duration_ms=listening_event_schema.duration_ms,
                spotify_track_data=[
                    SpotifyTrackData(
                        spotify_uri=listening_event_schema.spotify_track_id,
                        explicit=listening_event_schema.explicit,
                    )
                ],
                artists=artists,
                albums=[album],
            )
            logger.debug(f"Created track: {track}")
            
            session.add(track)
            spotify_track_id_cache[key] = track
            schema_track_map[listening_event_schema] = track
            
        return schema_track_map

    async def get_or_create_podcasts(self, session: AsyncSession, podcast_names: Sequence[str]) -> dict[str, Podcast]:
        # returning a dict from name to model works because podcast names are unique in our schema
        logger.debug(f"Getting or creating podcasts for {len(podcast_names)} podcasts...")
        
        # GET PODCASTS FROM DB
        statement = (
            select(Podcast)
            .where(Podcast.podcast_name.in_(podcast_names))
        )
        result = await session.execute(statement)
        podcasts_in_db = result.scalars().all()
        podcast_map = {podcast.podcast_name: podcast for podcast in podcasts_in_db}
        logger.debug(f"Found {len(podcasts_in_db)} podcasts in DB...")
        
        # CREATE PODCASTS NOT IN DB
        for podcast_name in podcast_names:
            if podcast_name not in podcast_map:
                new_podcast = Podcast(podcast_name=podcast_name)
                session.add(new_podcast)
                podcast_map[podcast_name] = new_podcast
        logger.debug(f"Created {len(podcast_map) - len(podcasts_in_db)} new podcasts...")
                
        return podcast_map

    async def create_podcast_episodes(self, session: AsyncSession, listening_event_schemas: Sequence[SpotifyListeningEventSchema]):
        logger.debug(f"Creating {len(listening_event_schemas)} podcast episodes...")
        podcast_map = await self.get_or_create_podcasts(
            session,
            [listening_event_schema.collection_name for listening_event_schema in listening_event_schemas]
        )
        
        spotify_episode_id_cache = {}
        schema_episode_map = {}
        for listening_event_schema in listening_event_schemas:
            logger.debug(f"Creating episode for schema: {listening_event_schema}")
            # using the cache like this leads to listening events with the same spotify_track_id to only be processed once
            key = listening_event_schema.spotify_track_id
            if key in spotify_episode_id_cache:
                logger.debug(f"Found episode in current cache: {listening_event_schema.track_name}")
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
            logger.debug(f"Created episode: {episode}")
            
            session.add(episode)
            spotify_episode_id_cache[key] = episode
            schema_episode_map[listening_event_schema] = episode
            
        return schema_episode_map

    async def get_or_create_audiobooks(self, session: AsyncSession, audiobook_titles: Sequence[str]) -> dict[str, Audiobook]:
        # returning a dict from name to model works because audiobook names are unique in our schema
        logger.debug(f"Getting or creating audiobooks for {len(audiobook_titles)} audiobooks...")
        
        # GET AUDIOBOOKS FROM DB
        statement = (
            select(Audiobook)
            .where(Audiobook.audiobook_title.in_(audiobook_titles))
        )
        result = await session.execute(statement)
        audiobooks_in_db = result.scalars().all()
        audiobook_map = {audiobook.audiobook_title: audiobook for audiobook in audiobooks_in_db}
        logger.debug(f"Found {len(audiobooks_in_db)} audiobooks in DB...")
        
        # CREATE AUDIOBOOKS NOT IN DB
        for audiobook_title in audiobook_titles:
            if audiobook_title not in audiobook_map:
                new_audiobook = Audiobook(audiobook_title=audiobook_title)
                session.add(new_audiobook)
                audiobook_map[audiobook_title] = new_audiobook
        logger.debug(f"Created {len(audiobook_map) - len(audiobooks_in_db)} new audiobooks...")
                
        return audiobook_map

    async def create_audiobook_chapters(self, session: AsyncSession, listening_event_schemas: Sequence[SpotifyListeningEventSchema]):
        logger.debug(f"Creating {len(listening_event_schemas)} audiobook chapters...")
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
                logger.debug(f"Found chapter in current cache: {listening_event_schema.track_name}")
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
            logger.debug(f"Created chapter: {chapter}")
            
            session.add(chapter)
            spotify_chapter_id_cache[key] = chapter
            schema_chapter_map[listening_event_schema] = chapter
            
        return schema_chapter_map

    async def _get_or_create_media(self, session: AsyncSession, media_type: MediaType, schemas_of_media_type: Sequence[SpotifyListeningEventSchema]):
        """Encapsulates the logic of finding or creating the media object."""
        
        logger.debug(f"Getting or creating media of type {media_type} for {len(schemas_of_media_type)} listening events...")
        creator = {
            MediaType.MUSIC_TRACK: self.create_tracks,
            MediaType.PODCAST_EPISODE: self.create_podcast_episodes,
            MediaType.AUDIOBOOK_CHAPTER: self.create_audiobook_chapters,
        }.get(media_type)
        if not creator:
            error = ValueError(f"Unsupported media type: {media_type}")
            logger.exception(error)
            raise error
        
        logger.debug(f"Using creator: {creator}")
        
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
        logger.debug(f"Inserting {len(schemas)} listening events in batches of {BATCH_SIZE}...")
        
        for i in range(0, len(schemas), BATCH_SIZE):
            batch = schemas[i:i + BATCH_SIZE]
            await self._insert_batch(session, batch)
        
    async def _insert_batch(self, session: AsyncSession, schemas: Sequence[SpotifyListeningEventSchema]) -> None:
        logger.debug(f"Inserting {len(schemas)} listening events...")
        media_types_in_data = set(schema.media_type for schema in schemas)
        
        for media_type in media_types_in_data:
            logger.debug(f"Inserting listening events of type {media_type}...")
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
            
            logger.debug(f"Preparing ListeningEvent data for upsert.media_id_col: {media_id_col}, model_primary_key_attr: {model_primary_key_attr}")
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

            logger.debug(f"Inserted {len(inserted_ids)} listening events...")
            logger.debug(f"Inserting listening event data for {len(inserted_ids)} listening events...")
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