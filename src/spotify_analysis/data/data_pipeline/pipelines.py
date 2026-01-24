from dataclasses import dataclass

from .getter import Getter, IdentityGetter
from .parser import Parser, SpotifyListeningHistoryParser
from .transformer import DataTransformer, SpotifyListeningHistoryTransformer
from .loader import Loader, SpotifyListeningHistoryLoader

@dataclass
class DataPipeline[G, P, T]:
    getter: Getter[G]
    parser: Parser[G, P]
    transformer: DataTransformer[P, T]
    loader: Loader[T]
    
    async def run(self):
        data = await self.getter.get_data()
        listening_history_df = self.parser.parse_data(data)
        transformed_listening_history_df = self.transformer.transform_data(listening_history_df)
        await self.loader.insert_listening_events(transformed_listening_history_df)
    
spotify_file_pipeline = DataPipeline(
    getter=IdentityGetter(),
    parser=SpotifyListeningHistoryParser(),
    transformer=SpotifyListeningHistoryTransformer(),
    loader=SpotifyListeningHistoryLoader()
)

spotify_api_uri_pipeline = DataPipeline(
    getter=SpotifyAPIGetter(),
    parser=SpotifyAPIParser(),
    transformer=SpotifyAPITransformer(),
    loader=SpotifyAPILoader(),
)

musicbrainz_api_isrc_pipeline = DataPipeline(
    getter=MusicbrainzAPIGetter(),
    parser=MusicbrainzAPIParser(),
    transformer=MusicbrainzAPITransformer(),
    loader=MusicbrainzAPILoader(),
)