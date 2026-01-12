from enum import Enum
import io
from dataclasses import dataclass

from .listening_event import ListeningEventSchema, SpotifyListeningEventSchema
from .parser import Parser, SpotifyListeningHistoryParser
from .enricher import Enricher
from .transformer import DataTransformer, SpotifyDataTransformer
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
    listening_event: type[ListeningEventSchema]
    parser: type[Parser]
    enricher: type[Enricher]
    transformer: type[DataTransformer]
    loader: type[Loader]

service_data_pipelines = {
    Service.SPOTIFY: DataPipeline(
        listening_event=SpotifyListeningEventSchema,
        parser=SpotifyListeningHistoryParser,
        transformer=SpotifyDataTransformer,
        loader=SpotifyLoader,
    )
}

assert all(service in service_data_pipelines for service in Service)