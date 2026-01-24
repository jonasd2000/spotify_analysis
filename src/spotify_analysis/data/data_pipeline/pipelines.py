from dataclasses import dataclass

from .getter import Getter, IdentityGetter
from .parser import Parser, SpotifyListeningHistoryParser
from .transformer import DataTransformer, SpotifyDataTransformer
from .loader import Loader, SpotifyLoader

@dataclass
class DataPipeline:
    getter: Getter
    parser: Parser
    transformer: DataTransformer
    loader: Loader
    
spotify_file_pipeline = DataPipeline(
    getter=IdentityGetter(),
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