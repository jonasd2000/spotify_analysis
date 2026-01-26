from abc import ABC, abstractmethod
import asyncio
import datetime
import logging
from typing import Sequence, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, async_sessionmaker

from .listening_event import ListeningEventSchema, MediaType, SpotifyListeningEventSchema
from spotify_analysis.data.worker import Worker
from spotify_analysis.data.models import (
    Track, SpotifyTrackData, 
    Artist, SpotifyArtistData,
    Album, SpotifyAlbumData,
    PodcastEpisode, SpotifyPodcastEpisodeData, Podcast,
    AudiobookChapter, SpotifyAudiobookChapterData, Audiobook,
    ListeningEvent, ListeningEventData,
)


logger = logging.getLogger(__name__)


class Loader[T: ListeningEventSchema](ABC):
    batch_size: int
    num_workers: int
    
    def __init__(self, batch_size: int = 1, num_workers: int = 1):
        super().__init__()
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0")
        if num_workers <= 0:
            raise ValueError("num_workers must be greater than 0")
        self.batch_size = batch_size
        self.num_workers = num_workers
        
    @abstractmethod
    async def _insert_batch(self, items: list[T]) -> None:
        ...
    
    async def _insert_batch_wrapper(self, items: list[T]) -> None:
        await self._insert_batch(items)
    
    async def insert_listening_events(self, schemas_queue: asyncio.Queue[T]) -> None:
        worker = Worker(schemas_queue, self.batch_size, strict=True, batch_processor=self._insert_batch_wrapper)
        async with asyncio.TaskGroup() as tg:
            for _ in range(self.num_workers):
                tg.create_task(worker())
    
class NullLoader[T: ListeningEventSchema](Loader[T]):
    async def _insert_batch(self, items):
        pass
    
class DatabaseLoader[T: ListeningEventSchema](Loader[T]):
    db_url: str
    engine: AsyncEngine
    session: async_sessionmaker[AsyncSession]
    
    def __init__(self, engine: AsyncEngine, batch_size: int = 1, num_workers: int = 1):
        super().__init__(batch_size, num_workers)
        self.engine = engine
        self.session = async_sessionmaker(self.engine, expire_on_commit=False)
        
    async def _insert_batch_wrapper(self, items):
        async with self.session() as session:
            await self._insert_batch(items, session)
            await session.commit()
    
class SpotifyListeningHistoryLoader(DatabaseLoader[SpotifyListeningEventSchema]):
    def __init__(self, db_url: str, num_workers = 1):
        SQLITE_PARAMETER_LIMIT = 32766
        MAX_PARAMETERS = 4  # in insert_batch, listening_event_data has the most parameters (4) that are inserted at once
        batch_size = SQLITE_PARAMETER_LIMIT // MAX_PARAMETERS
        super().__init__(db_url, batch_size, num_workers)
        
    async def get_media(self, session: AsyncSession, media_type: MediaType, listening_event_schemas: Sequence[SpotifyListeningEventSchema]) -> dict[SpotifyListeningEventSchema, Track | PodcastEpisode | AudiobookChapter]:
        logger.debug(f"Getting media for {media_type} for {len(listening_event_schemas)} listening events...")
        match media_type:
            case MediaType.MUSIC_TRACK:
                schema_media = {}
                # tracks_by_isrc_statement = (
                #     select(Track)
                #     .options(selectinload(Track.spotify_track_data), selectinload(Track.artists), selectinload(Track.albums))
                #     .where(Track.international_standard_recording_code.in_([schema.isrc for schema in listening_event_schemas if schema.isrc is not None]))
                # )
                # tracks_by_isrc_result = await session.execute(tracks_by_isrc_statement)
                # tracks_by_isrc = tracks_by_isrc_result.scalars().all()
                # isrc_track_map = {track.international_standard_recording_code: track for track in tracks_by_isrc}
                
                tracks_by_spotify_uri_statement = (
                    select(Track)
                    .options(selectinload(Track.spotify_track_data), selectinload(Track.artists), selectinload(Track.albums))
                    .join(SpotifyTrackData, Track.track_id == SpotifyTrackData.track_id)
                    .where(SpotifyTrackData.spotify_uri.in_([schema.spotify_track_id for schema in listening_event_schemas]))
                )
                tracks_by_spotify_uri_result = await session.execute(tracks_by_spotify_uri_statement)
                tracks_by_spotify_uri = tracks_by_spotify_uri_result.scalars().all()
                
                track_id_track_map = {}
                for track in tracks_by_spotify_uri:
                    for spotify_track_data in track.spotify_track_data:
                        track_id_track_map[spotify_track_data.spotify_uri] = track
                
                for schema in listening_event_schemas:
                    if schema.spotify_track_id in track_id_track_map:
                        schema_media[schema] = track_id_track_map[schema.spotify_track_id]
                    # elif schema.isrc in isrc_track_map:
                    #     schema_media[schema] = isrc_track_map[schema.isrc]
                        
                logger.debug(f"Found {schema_media} in db")
                        
                return schema_media
            
            case MediaType.PODCAST_EPISODE:
                tracks_by_isrc_statement = (
                    select(PodcastEpisode)
                    .options(selectinload(PodcastEpisode.spotify_podcast_episode_data))
                    .join(SpotifyPodcastEpisodeData, PodcastEpisode.episode_id == SpotifyPodcastEpisodeData.episode_id)
                    .where(SpotifyPodcastEpisodeData.spotify_episode_id.in_([schema.spotify_track_id for schema in listening_event_schemas]))
                )
                tracks_by_isrc_result = await session.execute(tracks_by_isrc_statement)
                spotify_podcast_episode_data = tracks_by_isrc_result.scalars().all()
                spotify_podcast_episode_map = {episode.spotify_podcast_episode_data.spotify_episode_id: episode for episode in spotify_podcast_episode_data}
                schema_episode_map = {
                    schema: spotify_podcast_episode_map[schema.spotify_track_id]
                    for schema in listening_event_schemas
                    if schema.spotify_track_id in spotify_podcast_episode_map
                }
                
                return schema_episode_map
                
            case MediaType.AUDIOBOOK_CHAPTER:
                tracks_by_isrc_statement = (
                    select(AudiobookChapter)
                    .options(selectinload(AudiobookChapter.spotify_audiobook_chapter_data))
                    .join(SpotifyAudiobookChapterData, AudiobookChapter.chapter_id == SpotifyAudiobookChapterData.chapter_id)
                    .where(SpotifyAudiobookChapterData.spotify_chapter_id.in_([schema.spotify_track_id for schema in listening_event_schemas]))
                )
                tracks_by_isrc_result = await session.execute(tracks_by_isrc_statement)
                spotify_audiobook_chapter_data = tracks_by_isrc_result.scalars().all()
                spotify_audiobook_chapter_map = {chapter.spotify_audiobook_chapter_data.spotify_chapter_id: chapter for chapter in spotify_audiobook_chapter_data}
                schema_chapter_map = {
                    schema: spotify_audiobook_chapter_map[schema.spotify_track_id]
                    for schema in listening_event_schemas
                    if schema.spotify_track_id in spotify_audiobook_chapter_map
                }
                
                return schema_chapter_map
            case _:
                raise ValueError(f"Unknown track type: {track_type}")
    
    async def get_or_create_artists(self, session: AsyncSession, artists: Sequence[str]) -> dict[str, Artist]:
        logger.debug(f"Getting or creating artists for {len(artists)} artists...")
        
        # GET ARTISTS FROM DB
        statement = (
            select(Artist)
            .where(Artist.artist_name.in_(artists))
        )
        result = await session.execute(statement)
        artists_in_db = result.scalars().all()
        artist_map = {artist.artist_name: artist for artist in artists_in_db}
        logger.debug(f"Found {len(artists_in_db)} artists in DB...")
        
        # CREATE ARTISTS NOT IN DB
        for artist_name in artists:
            if artist_name not in artist_map:
                new_artist = Artist(
                    artist_name=artist_name,
                )
                artist_map[artist_name] = new_artist
                session.add(new_artist)
        logger.debug(f"Created {len(artist_map) - len(artists_in_db)} new artists...")
                
        return artist_map
            
    def parse_date(self, date_str: str, precision: str) -> Optional[datetime.date]:
        if date_str is None:
            return None
        
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
    
    async def get_or_create_albums(self, session: AsyncSession, albums: Sequence[str]) -> dict[str, Album]:
        logger.debug(f"Getting or creating albums for {len(albums)} albums...")
        
        # GET ALBUMS FROM DB
        statement = (
            select(Album)
            .where(Album.album_name.in_(albums))
        )
        result = await session.execute(statement)
        albums_in_db = result.scalars().all()
        album_map = {album.album_name: album for album in albums_in_db}
        logger.debug(f"Found {len(albums_in_db)} albums in DB...")
        
        # CREATE ALBUMS NOT IN DB
        for album_name in albums:
            # album_uri = album["uri"]
            if album_name not in album_map:
                # album_name = album["name"]
                # album_type = album.get("album_type")
                # total_tracks = album.get("total_tracks")
                # release_date = album.get("release_date")
                # release_date_precision = album.get("release_date_precision")
                
                # release_date = self.parse_date(release_date, release_date_precision)
                
                new_album = Album(
                    album_name=album_name,
                )
                album_map[album_name] = new_album
                session.add(new_album)
        logger.debug(f"Created {len(album_map) - len(albums_in_db)} new albums...")
        
        return album_map
            
    def amend_track_information(self, track: Track, spotify_uri: str, explicit: bool, album: Album, artists: Sequence[Artist]) -> None:
        logger.debug(f"Amending track information for {track.track_name}...")
        if spotify_uri not in [data.spotify_uri for data in track.spotify_track_data]:
            logger.debug(f"Adding spotify track data for {track.track_name}...")
            spotify_track_data = SpotifyTrackData(
                spotify_uri=spotify_uri,
                explicit=explicit,
                track=track
            )
            track.spotify_track_data.append(spotify_track_data)
        if album and (album not in track.albums):
            logger.debug(f"Adding album {album.album_name} for {track.track_name}...")
            track.albums.append(album)
        for artist in artists:
            if artist and (artist not in track.artists):
                logger.debug(f"Adding artist {artist.artist_name} for {track.track_name}...")
                track.artists.append(artist)
            
    async def create_tracks(self, session: AsyncSession, listening_event_schemas: Sequence[SpotifyListeningEventSchema], existing_media: list[Track]) -> dict[SpotifyListeningEventSchema, Track]:
        logger.debug(f"Creating {len(listening_event_schemas)} tracks...")
        artist_map = await self.get_or_create_artists(
            session,
            [
                artist
                for listening_event_schema in listening_event_schemas
                for artist in listening_event_schema.creators
            ]
        )
        album_map = await self.get_or_create_albums(
            session,
            [listening_event_schema.collection_name for listening_event_schema in listening_event_schemas]
        )
        
        # isrc_cache: dict[str, Track] = {}
        # for track in existing_media:
        #     if track.international_standard_recording_code is None:
        #         continue
        #     isrc_cache[track.international_standard_recording_code] = track
        
        spotify_uri_cache: dict[str, Track] = {}
        for track in existing_media:
            for spotify_track_data in track.spotify_track_data:
                spotify_uri_cache[spotify_track_data.spotify_uri] = track
        schema_track_map = {}
        for listening_event_schema in listening_event_schemas:
            logger.debug(f"Creating track for schema: {listening_event_schema}")
            # using the cache like this leads to listening events with the same spotify_track_id to only be processed once
            if listening_event_schema.spotify_track_id in spotify_uri_cache:
                logger.debug(f"Found track in spotify_uri_cache: {listening_event_schema.spotify_track_id}")
                schema_track_map[listening_event_schema] = spotify_uri_cache[listening_event_schema.spotify_track_id]
                continue
            
            # if listening_event_schema.isrc in isrc_cache:
            #     # also means that this is a new spotify uri
            #     logger.debug(f"Found track in isrc_cache: {listening_event_schema.isrc}")
            #     track: Track = isrc_cache[listening_event_schema.isrc]
            #     self.amend_track_information(
            #         track=track,
            #         spotify_uri=listening_event_schema.spotify_track_id,
            #         explicit=listening_event_schema.explicit,
            #         album=album_map.get(listening_event_schema.album["uri"]),
            #         artists=[artist_map.get(artist["uri"]) for artist in listening_event_schema.artists],
            #     )
            #     spotify_uri_cache[listening_event_schema.spotify_track_id] = track
            #     schema_track_map[listening_event_schema] = track
            #     continue
            
            artists = [artist_map.get(artist) for artist in listening_event_schema.creators]
            album = album_map.get(listening_event_schema.collection_name)
            
            track = Track(
                track_name=listening_event_schema.track_name,
                # international_standard_recording_code=listening_event_schema.isrc,
                # duration_ms=listening_event_schema.duration_ms,
                spotify_track_data=[
                    SpotifyTrackData(
                        spotify_uri=listening_event_schema.spotify_track_id,
                        # explicit=listening_event_schema.explicit,
                    )
                ],
                artists=artists,
                albums=[album],
            )
            logger.debug(f"Created track: {track}")
            
            session.add(track)
            spotify_uri_cache[listening_event_schema.spotify_track_id] = track
            # isrc_cache[listening_event_schema.isrc] = track
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

    async def create_podcast_episodes(self, session: AsyncSession, listening_event_schemas: Sequence[SpotifyListeningEventSchema], existing_media: list[PodcastEpisode]):
        logger.debug(f"Creating {len(listening_event_schemas)} podcast episodes...")
        podcast_map = await self.get_or_create_podcasts(
            session,
            [listening_event_schema.collection_name for listening_event_schema in listening_event_schemas]
        )
        
        spotify_episode_id_cache = {}
        for episode in existing_media:
            if episode.spotify_podcast_episode_data is None:
                continue
            spotify_episode_id_cache[episode.spotify_podcast_episode_data.spotify_episode_id] = episode
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

    async def create_audiobook_chapters(self, session: AsyncSession, listening_event_schemas: Sequence[SpotifyListeningEventSchema], existing_media: list[AudiobookChapter]):
        logger.debug(f"Creating {len(listening_event_schemas)} audiobook chapters...")
        audiobook_map = await self.get_or_create_audiobooks(
            session,
            [listening_event_schema.collection_name for listening_event_schema in listening_event_schemas]
        )
        
        spotify_chapter_id_cache = {}
        for chapter in existing_media:
            if chapter.spotify_audiobook_chapter_data is None:
                continue
            spotify_chapter_id_cache[chapter.spotify_audiobook_chapter_data.spotify_chapter_id] = chapter
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

        # CREATING MEDIA
        # Dispatch to the appropriate creator based on type
        
        created_schema_track_map = await creator(session, schemas_of_media_type, existing_media=schema_media.values())
        schema_media.update(created_schema_track_map)
            
        return schema_media
        
    async def _insert_batch(self, schemas_batch: Sequence[SpotifyListeningEventSchema], session: AsyncSession) -> None:
        logger.debug(f"Inserting {len(schemas_batch)} listening events...")
        media_types_in_data = set(schema.media_type for schema in schemas_batch)
        
        for media_type in media_types_in_data:
            logger.debug(f"Inserting listening events of type {media_type}...")
            # 1. Resolve Media (Still ORM-centric)
            schemas_of_media_type = [schema for schema in schemas_batch if schema.media_type == media_type]

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
            