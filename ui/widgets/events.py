from enum import Enum

class EventType(Enum):
    DATA_ADDED = "data_added"
    ARTIST_SELECTED = "artist_selected"
    TRACK_SELECTED = "track_selected"