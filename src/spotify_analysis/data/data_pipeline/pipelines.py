import asyncio
from dataclasses import dataclass
from typing import Literal, Optional, Awaitable

from spotify_analysis.data.worker import Worker, queue_splitter
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
    
    hooks: dict[str, list[asyncio.Queue]]
    
    def __post_init__(self):
        self.hooks = {}
        self.stages = {
            "getter": self.getter,
            "parser": self.parser,
            "transformer": self.transformer,
            "loader": self.loader
        }
    
    def register_hook(self, on: Literal["getter", "parser", "transformer"], queue: asyncio.Queue):
        if on not in self.hooks:
            self.hooks[on] = []
        self.hooks[on].append(queue)
    
    def _create_hook(self, stage: str, queue: asyncio.Queue) -> tuple[asyncio.Queue, Optional[Awaitable[None]]]:
        corr = None
        if stage in self.hooks and self.hooks[stage]:
            getter_hook_worker = Worker(queue, 10000, strict=False, batch_processor=queue_splitter)
            queue = asyncio.Queue()
            hook_queues = self.hooks["getter"] + [queue]
            corr = getter_hook_worker(*hook_queues)
        queue, corr
    
    async def run(self, input_queue: asyncio.Queue[R]):
        got_queue = asyncio.Queue()
        parsed_queue = asyncio.Queue()
        transformed_queue = asyncio.Queue()
        
        got_queue, got_hook_worker = self._create_hook("getter", got_queue)
        parsed_queue, parsed_hook_worker = self._create_hook("parser", parsed_queue)
        transformed_queue, transformed_hook_worker = self._create_hook("transformer", transformed_queue)
        
        async with asyncio.TaskGroup() as tg:
            for worker in filter(lambda x: x is not None, [got_hook_worker, parsed_hook_worker, transformed_hook_worker]):
                tg.create_task(worker)
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