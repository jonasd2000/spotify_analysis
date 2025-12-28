import datetime
from enum import Enum
from typing import Optional

import polars as pl
from poldantic import to_polars_schema
import pydantic

class TrackType(Enum):
    SONG = "song"
    PODCAST_EPISODE = "podcast_episode"
    AUDIOBOOK_CHAPTER = "audiobook_chapter"

class ListeningEventSchema(pydantic.BaseModel):
    timestamp: datetime.datetime
    ms_played: int
    
    track_name: str
    creators: list[str]
    collection_name: str
    
    track_type: TrackType
    
listening_event_pl_schema = to_polars_schema(ListeningEventSchema)
listening_event_pl_schema.update({"ms_played": pl.UInt32, "timestamp": pl.Datetime()})
    
class SpotifyListeningEventSchema(ListeningEventSchema):
    spotify_track_id: str
    
    country: str
    platform: str
    ip_address: str
    
    reason_start: str
    reason_end: str
    shuffle: bool
    skipped: bool
    offline: bool
    offline_timestamp: Optional[str]
    incognito_mode: bool
    
spotify_listening_event_pl_schema = listening_event_pl_schema.copy()
# update the spotify listening event schema only with those keys that are not in listening_event_schema to avoid overwriting
spotify_listening_event_pl_schema.update({k: v for k,v in to_polars_schema(SpotifyListeningEventSchema).items() if k not in listening_event_pl_schema})