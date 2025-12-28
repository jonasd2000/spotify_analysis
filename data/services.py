from enum import Enum
import io
from dataclasses import dataclass

from .parser import Parser, SpotifyListeningHistoryParser
from .transformer import DataTransformer
from .listening_event import ListeningEvent, SpotifyListeningEvent

class Service(Enum):
    SPOTIFY = "spotify"
    
class ServiceNotFoundError(Exception):
    pass
    
def recognise_listening_history_service(file_name: str, file_content: io.BytesIO) -> Service:
    return Service.SPOTIFY

@dataclass
class DataPipeline:
    parser: type[Parser]
    listening_event: type[ListeningEvent]
    transformer: type[DataTransformer]

service_data_pipelines = {
    Service.SPOTIFY: DataPipeline(
        parser=SpotifyListeningHistoryParser,
        listening_event=SpotifyListeningEvent,
        transformer=None,
    )
}

assert all(service in service_data_pipelines for service in Service)