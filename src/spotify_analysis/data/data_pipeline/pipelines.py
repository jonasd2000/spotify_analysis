import asyncio
from typing import Literal, Optional

from spotify_analysis.data.worker import Worker, queue_splitter
from .getter import Getter
from .parser import Parser
from .transformer import DataTransformer
from .loader import Loader

class DataPipeline[R, G, P, T]:
    getter: Getter[R, G]
    parser: Parser[G, P]
    transformer: DataTransformer[P, T]
    loader: Loader[T]
    
    hooks: dict[str, list[asyncio.Queue]]
    
    def __init__(self, getter: Getter[R, G], parser: Parser[G, P], transformer: DataTransformer[P, T], loader: Loader[T]):
        self.getter = getter
        self.parser = parser
        self.transformer = transformer
        self.loader = loader
        
        self.hooks = {}
        self.stages = {
            "getter": self.getter,
            "parser": self.parser,
            "transformer": self.transformer,
            "loader": self.loader
        }
    
    def register_hook(self, on: Literal["getter", "parser", "transformer"], queue: asyncio.Queue):
        """
        Registers a hook for a given stage in the pipeline.

        Args:
            on: The stage for which the hook is being registered.
            queue: The queue to which the output of the stage should be sent.

        The hook will be executed in the order in which it was registered.
        """
        
        if on not in self.hooks:
            self.hooks[on] = []
        self.hooks[on].append(queue)
    
    def _create_hooks(self, stage: Literal["getter", "parser", "transformer"], queue: asyncio.Queue) -> tuple[asyncio.Queue, Optional[Worker], Optional[list[asyncio.Queue]]]:
        """
        Creates a hook for a given stage in the pipeline.

        Args:
            stage: The stage for which the hook is being created.
            queue: The queue to which the hook should write its output.

        Returns:
            A tuple containing the queue to which the hook should write its output, an optional Worker object for the hook, and an optional list of queues to which the hook should write its output.
        """
        
        getter_hook_worker = None
        hooked_queues = None
        if stage in self.hooks and self.hooks[stage]:
            getter_hook_worker = Worker(queue, 10000, strict=False, batch_processor=queue_splitter)
            queue = asyncio.Queue()
            hooked_queues = self.hooks["getter"] + [queue]
        return queue, getter_hook_worker, hooked_queues
    
    async def _dispatch_hook_worker(self, worker: Worker, output_queues: list[asyncio.Queue]):
        async with asyncio.TaskGroup() as tg:
            tg.create_task(worker(*output_queues))
        for queue in output_queues:
            queue.shutdown()
    
    async def run(self, input_queue: asyncio.Queue[R]):
        got_queue = asyncio.Queue()
        parsed_queue = asyncio.Queue()
        transformed_queue = asyncio.Queue()
        
        split_got_queue, *getter_hook = self._create_hooks("getter", got_queue)
        split_parsed_queue, *parser_hook = self._create_hooks("parser", parsed_queue)
        split_transformed_queue, *transformer_hook = self._create_hooks("transformer", transformed_queue)
        
        async with asyncio.TaskGroup() as tg:
            for i, hook in enumerate(filter(lambda x: x[0] is not None, [getter_hook, parser_hook, transformer_hook])):
                worker, hooked_queues = hook
                tg.create_task(self._dispatch_hook_worker(worker, hooked_queues), name=f"pipeline-hook-{i+1}")
            tg.create_task(self.getter.get_data(input_queue, got_queue), name="pipeline-getter")
            tg.create_task(self.parser.parse_data(split_got_queue, parsed_queue), name="pipeline-parser")
            tg.create_task(self.transformer.transform_data(split_parsed_queue, transformed_queue), name="pipeline-transformer")
            tg.create_task(self.loader.insert_listening_events(split_transformed_queue), name="pipeline-loader")

# spotify_api_uri_pipeline = DataPipeline(
#     getter=SpotifyAPIGetter(),
#     parser=SpotifyAPIParser(),
#     transformer=SpotifyAPITransformer(),
#     loader=SpotifyAPILoader(),
# )

# musicbrainz_api_isrc_pipeline = DataPipeline(
#     getter=MusicbrainzAPIGetter(),
#     parser=MusicbrainzAPIParser(),
#     transformer=MusicbrainzAPITransformer(),
#     loader=MusicbrainzAPILoader(),
# )