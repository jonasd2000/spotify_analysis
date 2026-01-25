import asyncio
from dataclasses import dataclass

from .getter import Getter, IdentityGetter, SpotifyAPIGetter
from .parser import Parser, SpotifyListeningHistoryParser
from .transformer import DataTransformer, SpotifyListeningHistoryTransformer
from .loader import Loader, SpotifyListeningHistoryLoader

@dataclass
class DataPipeline[R, G, P, T]:
    getter: Getter[R, G]
    parser: Parser[G, P]
    transformer: DataTransformer[P, T]
    loader: Loader[T]
    
    async def run(self, input_queue: asyncio.Queue[R]):
        got_queue = asyncio.Queue()
        parsed_queue = asyncio.Queue()
        transformed_queue = asyncio.Queue()
        
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.getter.get_data(input_queue, got_queue))
            tg.create_task(self.parser.parse_data(got_queue, parsed_queue))
            tg.create_task(self.transformer.transform_data(parsed_queue, transformed_queue))
            tg.create_task(self.loader.insert_listening_events(transformed_queue))
    
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