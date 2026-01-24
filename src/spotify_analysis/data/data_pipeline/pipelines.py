from dataclasses import dataclass

from .getter import Getter, IdentityGetter
from .parser import Parser, SpotifyListeningHistoryParser
from .transformer import DataTransformer, SpotifyDataTransformer
from .loader import Loader, SpotifyLoader

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