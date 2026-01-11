from enum import Enum
import io
from dataclasses import dataclass

from .parser import Parser, SpotifyListeningHistoryParser
from .transformer import DataTransformer, SpotifyDataTransformer
from .listening_event import ListeningEventSchema, SpotifyListeningEventSchema
from .loader import Loader, SpotifyLoader

class Service(Enum):
    SPOTIFY = "spotify"
    
class ServiceNotFoundError(Exception):
    pass
    
def recognise_listening_history_service(file_name: str) -> Service | None:
    if ("Streaming_History_Audio" in file_name):
        return Service.SPOTIFY

    return None

@dataclass
class DataPipeline:
    parser: type[Parser]
    listening_event: type[ListeningEventSchema]
    transformer: type[DataTransformer]
    loader: type[Loader]

service_data_pipelines = {
    Service.SPOTIFY: DataPipeline(
        parser=SpotifyListeningHistoryParser,
        listening_event=SpotifyListeningEventSchema,
        transformer=SpotifyDataTransformer,
        loader=SpotifyLoader,
    )
}

assert all(service in service_data_pipelines for service in Service)