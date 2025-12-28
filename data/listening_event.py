from enum import Enum
from typing import Optional

import polars as pl
from poldantic import to_polars_schema
import pydantic

class TrackType(Enum):
    SONG = "song"
    PODCAST_EPISODE = "podcast_episode"
    AUDIOBOOK_CHAPTER = "audiobook_chapter"

class ListeningEvent(pydantic.BaseModel):
    timestamp: str
    ms_played: int
    
    track_name: str
    creator: str
    collection_name: str
    
    track_type: TrackType
    
listening_event_schema = to_polars_schema(ListeningEvent)
listening_event_schema.update({"ms_played": pl.UInt32})
    
class SpotifyListeningEvent(ListeningEvent):
    spotify_track_id: str
    
    country: str
    platform: str
    ip_address: str
    
    reason_start: str
    reason_end: str
    shuffle: bool
    skipped: bool
    offline: bool
    offline_timestamp: str
    incognito_mode: bool
    
spotify_listening_event_schema = listening_event_schema.copy()
# update the spotify listening event schema only with those keys that are not in listening_event_schema to avoid overwriting
spotify_listening_event_schema.update({k: v for k,v in to_polars_schema(SpotifyListeningEvent).items() if k not in listening_event_schema})
spotify_listening_event_schema = pl.Schema(spotify_listening_event_schema)