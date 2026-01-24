from enum import Enum


class Service(Enum):
    SPOTIFY = "spotify"
    
class ServiceNotFoundError(Exception):
    pass
    
def recognise_listening_history_service(file_name: str) -> Service | None:
    if ("Streaming_History_Audio" in file_name):
        return Service.SPOTIFY

    return None
