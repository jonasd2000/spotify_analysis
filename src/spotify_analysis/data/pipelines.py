from dataclasses import dataclass

from .listening_event import ListeningEventSchema, SpotifyListeningEventSchema
from .parser import Parser, SpotifyListeningHistoryParser
from .transformer import DataTransformer, SpotifyDataTransformer
from .loader import Loader, SpotifyLoader

@dataclass
class DataPipeline:
    parser: Parser
    transformer: DataTransformer
    loader: Loader
    
spotify_file_pipeline = DataPipeline(
    parser=SpotifyListeningHistoryParser(),
    transformer=SpotifyDataTransformer(),
    loader=SpotifyLoader()
)

spotify_api_uri_pipeline = DataPipeline(
    parser=SpotifyAPIParser(),
    transformer=SpotifyAPITransformer(),
    loader=SpotifyAPILoader(),
)

musicbrainz_api_isrc_pipeline = DataPipeline(
    parser=MusicbrainzAPIParser(),
    transformer=MusicbrainzAPITransformer(),
    loader=MusicbrainzAPILoader(),
)