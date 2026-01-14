from enum import Enum

class EventType(Enum):
    DATA_ADDED = "data_added"
    ARTIST_SELECTED = "artist_selected"
    TRACK_SELECTED = "track_selected"
    ANALYSE_TRACK_REQUEST = "analyse_track_request"
    START_FILE_LOAD = "start_file_load"
    END_FILE_LOAD = "end_file_load"