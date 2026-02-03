import asyncio
from dataclasses import dataclass
import logging
from itertools import pairwise
from typing import Callable, Literal

from spotify_analysis.data.worker import Worker, queue_splitter
from .pipeline_stage import AsyncPipelineStage
from .getter import Getter
from .parser import Parser
from .transformer import DataTransformer
from .loader import Loader


logger = logging.getLogger(__name__)


@dataclass
class QueuePair:
    input_queue: asyncio.Queue
    output_queue: asyncio.Queue
    
    def __iter__(self):
        yield self.input_queue
        yield self.output_queue


class PipelineModule:
    stages: list[AsyncPipelineStage]
    stage_queues: dict[AsyncPipelineStage, QueuePair]
    hooks: dict[AsyncPipelineStage, list[asyncio.Queue]]
    
    def __init__(self, stages: list[AsyncPipelineStage]):
        self.stages = stages
        self.stage_queues = self._setup_stage_queues()
        self.hooks = {}
    
    def _setup_stage_queues(self) -> dict[AsyncPipelineStage, QueuePair]:
        self.stage_queues = {QueuePair(None, None) for _ in self.stages}
        for i, (stage, next_stage) in enumerate(pairwise(self.stages)):
            stage_out_queue = asyncio.Queue()
            self._set_output_queue(stage, stage_out_queue)
            self._set_input_queue(next_stage, stage_out_queue)

        return self.stage_queues            
    
    def _set_input_queue[I, O](self, stage: AsyncPipelineStage[I, O], queue: asyncio.Queue[I]):
        self.stage_queues[stage].input_queue = queue
        
    def _get_input_queue(self, stage: AsyncPipelineStage):
        return self.stage_queues[stage].input_queue
        
    def _set_output_queue[I, O](self, stage: AsyncPipelineStage[I, O], queue: asyncio.Queue[O]):
        self.stage_queues[stage].output_queue = queue
        
    def _get_output_queue(self, stage: AsyncPipelineStage):
        return self.stage_queues[stage].output_queue
    
    def register_hook(self, on_index: int, queue: asyncio.Queue):
        """
        Registers a hook for a given stage in the pipeline.

        Args:
            on: The stage for which the hook is being registered.
            queue: The queue to which the output of the stage should be sent.

        The hook will be executed in the order in which it was registered.
        """
        
        stage = self.stages[on_index]
        
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
        
        for stage, next_stage in pairwise(self.stages): # does not include the last stage as stage, which i am currently fine with
            if stage not in self.hooks:
                continue
            stage_output_queue = self._get_output_queue(stage)
            
            hook_worker = Worker(stage_output_queue, 10000, strict=False, batch_processor=queue_splitter)
            
            next_stage_input_queue = asyncio.Queue()
            self._set_input_queue(next_stage, next_stage_input_queue)
            
            self.register_hook(stage, next_stage_input_queue)
            
            tg.create_task(self._dispatch_hook_worker(hook_worker, self.hooks[stage]))
    
    async def _dispatch_hook_worker(self, queue_splitter_worker: Worker, hooks: list[asyncio.Queue]):
        async with asyncio.TaskGroup() as tg:
            tg.create_task(queue_splitter_worker(hooks))
        for queue in hooks:
            queue.shutdown()
    
    async def run(self, input_queue: asyncio.Queue, output_queue: asyncio.Queue):
        logger.debug("Running pipeline...")
        self._set_input_queue(self.stages[0], input_queue)
        self._set_output_queue(self.stages[-1], output_queue)
        
        async with asyncio.TaskGroup() as tg:
            self._create_hooks(tg)
            
            for stage in self.stages:
                in_queue, out_queue = self.stage_queues[stage]
                logger.debug(f"Running {stage.__class__.__name__}...")
                tg.create_task(stage.run(in_queue, out_queue), name=f"pipeline-{stage.__class__.__name__}")

class DataPipeline:
    modules: list[PipelineModule]
    
    module_input_queues: dict[PipelineModule, asyncio.Queue]
    
    def __init__(self, main_module: PipelineModule):
        self.modules = [main_module]
        self.module_input_queues = {main_module: None}
    
    @property
    def main_module(self):
        return self.modules[0]
    
    def _set_module_input_queue(self, module: PipelineModule, queue: asyncio.Queue):
        self.module_input_queues[module] = queue
    
    def add_module(self, on: tuple[PipelineModule, int], module: PipelineModule):
        on_module, module_stage_index = on
        
        module_in_queue = asyncio.Queue()
        self.module_input_queues[module] = module_in_queue
        
        self.modules.append(module)
        on_module.register_hook(module_stage_index, module_in_queue)
        
    async def run(self, input_queue: asyncio.Queue):
        self._set_module_input_queue(self.main_module, input_queue)
        async with asyncio.TaskGroup() as tg:
            for module in self.modules:
                tg.create_task(module.run(self.module_input_queues[module], asyncio.Queue()))