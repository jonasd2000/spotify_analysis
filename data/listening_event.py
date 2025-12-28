from enum import Enum
from typing import Optional

import pydantic

class TrackType(Enum):
    SONG = "song"
    PODCAST_EPISODE = "podcast_episode"
    AUDIOBOOK_CHAPTER = "audiobook_chapter"
    
class ListeningEvent(pydantic.BaseModel):
    timestamp: str
    milliseconds_played: int
    
    track_name: str
    creator: str
    collection_name: str
    
    track_type: TrackType
    
class SpotifyListeningEvent(ListeningEvent):
    spotify_track_id: str
    listening_agent: Optional[str]
    
    reason_start: str
    reason_end: str
    shuffle: bool
    skipped: bool
    offline: bool
    offline_timestamp: str
    incognito_mode: bool
    
    