from dataclasses import dataclass

from .listening_event import ListeningEventSchema, SpotifyListeningEventSchema
from .parser import Parser, SpotifyListeningHistoryParser
from .enricher import SpotifyAPIEnricher
from .transformer import DataTransformer, SpotifyDataTransformer
from .loader import Loader, SpotifyLoader
from .services import Service

@dataclass
class DataPipeline:
    listening_event: type[ListeningEventSchema]
    parser: type[Parser]
    transformer: type[DataTransformer]
    loader: type[Loader]

service_data_pipelines = {
    Service.SPOTIFY: DataPipeline(
        listening_event=SpotifyListeningEventSchema,
        parser=SpotifyListeningHistoryParser,
        enricher=SpotifyAPIEnricher,
        transformer=SpotifyDataTransformer,
        loader=SpotifyLoader,
    )
}

assert all(service in service_data_pipelines for service in Service)