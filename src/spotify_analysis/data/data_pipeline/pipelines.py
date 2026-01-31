import asyncio
from dataclasses import dataclass
from typing import Literal
from itertools import pairwise

from spotify_analysis.data.worker import Worker, queue_splitter
from .pipeline_stage import AsyncPipelineStage
from .getter import Getter
from .parser import Parser
from .transformer import DataTransformer
from .loader import Loader

@dataclass
class QueuePair:
    input_queue: asyncio.Queue
    output_queue: asyncio.Queue
    
    def __iter__(self):
        yield self.input_queue
        yield self.output_queue


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
        
        got_queue = asyncio.Queue[G]()
        parsed_queue = asyncio.Queue[P]()
        transformed_queue = asyncio.Queue[T]()
        loaded_queue = asyncio.Queue[None]()
        
        self.stages: dict[AsyncPipelineStage, QueuePair] = {
            self.getter: QueuePair(None, got_queue),
            self.parser: QueuePair(got_queue, parsed_queue),
            self.transformer: QueuePair(parsed_queue, transformed_queue),
            self.loader: QueuePair(transformed_queue, loaded_queue)
        }
        
        self.hooks = {}
    
    def set_input_queue[I, O](self, stage: AsyncPipelineStage[I, O], queue: asyncio.Queue[I]):
        self.stages[stage].input_queue = queue
        
    def get_input_queue(self, stage: AsyncPipelineStage):
        return self.stages[stage].input_queue
        
    def set_output_queue[I, O](self, stage: AsyncPipelineStage[I, O], queue: asyncio.Queue[O]):
        self.stages[stage].output_queue = queue
        
    def get_output_queue(self, stage: AsyncPipelineStage):
        return self.stages[stage].output_queue
    
    def get_stage(self, stage: Literal["getter", "parser", "transformer", "loader"] | AsyncPipelineStage) -> AsyncPipelineStage:
        if stage is self.getter:
            return self.getter
        if stage is self.parser:
            return self.parser
        if stage is self.transformer:
            return self.transformer
        if stage is self.loader:
            return self.loader
        match stage:
            case "getter":
                return self.getter
            case "parser":
                return self.parser
            case "transformer":
                return self.transformer
            case "loader":
                return self.loader
            case _:
                raise ValueError(f"Unknown stage: {stage}")
    
    def register_hook(self, on: Literal["getter", "parser", "transformer"] | AsyncPipelineStage, queue: asyncio.Queue):
        """
        Registers a hook for a given stage in the pipeline.

        Args:
            on: The stage for which the hook is being registered.
            queue: The queue to which the output of the stage should be sent.

        The hook will be executed in the order in which it was registered.
        """
        
        stage = self.get_stage(on)
        
        if stage not in self.hooks:
            self.hooks[stage] = []
        self.hooks[stage].append(queue)
    
    def _create_hooks(self, tg: asyncio.TaskGroup) -> None:
        """
        Creates a hook for a given stage in the pipeline.

        Args:
            stage: The stage for which the hook is being created.
            queue: The queue to which the hook should write its output.

        Returns:
            A tuple containing the queue to which the hook should write its output, an optional Worker object for the hook, and an optional list of queues to which the hook should write its output.
        """
        
        for stage, next_stage in pairwise(self.stages): # does not include the last stage (loader) as stage, which i am currently fine with
            if stage not in self.hooks:
                continue
            stage_output_queue = self.get_output_queue(stage)
            
            hook_worker = Worker(stage_output_queue, 10000, strict=False, batch_processor=queue_splitter)
            
            next_stage_input_queue = asyncio.Queue()
            self.set_input_queue(next_stage, next_stage_input_queue)
            
            hooked_queues = self.hooks[stage] + [next_stage_input_queue]
            tg.create_task(self._dispatch_hook_worker(hook_worker, hooked_queues))
    
    async def _dispatch_hook_worker(self, worker: Worker, output_queues: list[asyncio.Queue]):
        async with asyncio.TaskGroup() as tg:
            tg.create_task(worker(*output_queues))
        for queue in output_queues:
            queue.shutdown()
    
    async def run(self, input_queue: asyncio.Queue[R]):
        self.set_input_queue(self.getter, input_queue)
        
        async with asyncio.TaskGroup() as tg:
            self._create_hooks(tg)
                
            for stage, (in_queue, out_queue) in self.stages.items():
                tg.create_task(stage.run(in_queue, out_queue), name=f"pipeline-{stage.__class__.__name__}")