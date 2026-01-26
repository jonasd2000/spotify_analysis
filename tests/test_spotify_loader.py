import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from spotify_analysis.data.data_pipeline.loader import SpotifyListeningHistoryLoader
from spotify_analysis.data.models import Base, Track, SpotifyTrackData
from spotify_analysis.data.data_pipeline.listening_event import SpotifyListeningEventSchema, MediaType

@pytest_asyncio.fixture
async def Session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, expire_on_commit=False)
    return session

@pytest.mark.asyncio
async def test_amend_track_information_spotify_data(Session):
    loader = SpotifyListeningHistoryLoader()
    
    async with Session() as session:
        track = Track(
            track_id=1, track_name="Test Track", international_standard_recording_code=None, 
            duration_ms=None, 
            spotify_track_data=[
                SpotifyTrackData(
                    spotify_track_data_id=1, 
                    track_id=1, 
                    spotify_uri="spotify:track:1", 
                    explicit=False
                )
            ],
            musicbrainz_track_data=None, 
            artists=[], albums=[], listening_events=[]
        )
        session.add(track)
        await session.flush()
        
        tracks = await session.execute(select(Track))
        assert len(tracks.scalars().all()) == 1
        spotify_track_data = await session.execute(select(SpotifyTrackData))
        assert len(spotify_track_data.scalars().all()) == 1
        
        loader.amend_track_information(
            track=track, 
            spotify_uri="spotify:track:2", 
            explicit=False, 
            album=None, 
            artists=[]
        )
        
        tracks = await session.execute(select(Track))
        assert len(tracks.scalars().all()) == 1
        spotify_track_data = await session.execute(select(SpotifyTrackData))
        assert len(spotify_track_data.scalars().all()) == 2
        
@pytest.mark.asyncio
async def test_create_tracks_amend_track_information(Session):
    loader = SpotifyListeningHistoryLoader()
    listening_event_schemas = [
        SpotifyListeningEventSchema.model_validate({"isrc": "12345678", "spotify_track_id": "spotify:track:1", "timestamp": datetime.datetime(2023, 1, 1), "ms_played": 1000, "track_name": "Test Track", "creators": [], "collection_name": "Test Collection", "media_type": MediaType.MUSIC_TRACK, "country": "DE", "platform": "Spotify", "ip_address": "abc", "reason_start": "1", "reason_end": "2", "shuffle": True, "skipped": False, "offline": False, "incognito_mode": False, "offline_timestamp": None, "name": "bla", "explicit": False, "duration_ms": 180000, "artists": [], "album": {"uri": "123456789", "name": "Test Album"}}),
        SpotifyListeningEventSchema.model_validate({"isrc": "12345678", "spotify_track_id": "spotify:track:2", "timestamp": datetime.datetime(2023, 1, 2), "ms_played": 1000, "track_name": "Test Track", "creators": [], "collection_name": "Test Collection", "media_type": MediaType.MUSIC_TRACK, "country": "DE", "platform": "Spotify", "ip_address": "abc", "reason_start": "1", "reason_end": "2", "shuffle": True, "skipped": False, "offline": False, "incognito_mode": False, "offline_timestamp": None, "name": "bla", "explicit": False, "duration_ms": 180000, "artists": [], "album": {"uri": "123456789", "name": "Test Album"}})
    ]
    async with Session() as session:
        schema_model_map = await loader.create_tracks(session=session, listening_event_schemas=listening_event_schemas, existing_media=[])
        
        tracks = await session.execute(select(Track))
        assert len(tracks.scalars().all()) == 1
        spotify_track_data = await session.execute(select(SpotifyTrackData))
        assert len(spotify_track_data.scalars().all()) == 2