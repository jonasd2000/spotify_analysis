from abc import abstractmethod
import asyncio
import logging
import time
from typing import Callable, Awaitable

from spotify_analysis.data.worker import Worker


logger = logging.getLogger(__name__)


class AsyncPipelineStage[I, O]:
    batch_size: int
    num_workers: int
    strict: bool
    
    wait_for: asyncio.Event
    finished_event: asyncio.Event
    process_items_fn: Callable[[list[I], asyncio.Queue[O]], Awaitable[None]]
    
    def __init__(self, batch_size: int, num_workers: int, strict: bool, wait_for: asyncio.Event = None):
        super().__init__()
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0")
        if num_workers <= 0:
            raise ValueError("num_workers must be greater than 0")
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.strict = strict
        self.process_items_fn = self._process_items
        self.wait_for = wait_for
        self.finished_event = asyncio.Event()
        
    @abstractmethod
    async def _process_item(self, item: I) -> O:
        ...
    
    async def _process_items(self, items: list[I], output_queue: asyncio.Queue[O]):
        logger.debug(f"{self.__class__.__name__} processing {len(items)} items...")
        for item in items:
            processed_item = await self._process_item(item)
            await self._put_processed_item_to_queue(processed_item, output_queue)
            
    async def _put_processed_item_to_queue(self, processed_item: O, output_queue: asyncio.Queue[O]):
        await output_queue.put(processed_item)
    
    async def run(self, input_queue: asyncio.Queue[I], output_queue: asyncio.Queue[O]):
        if self.wait_for is not None:
            await self.wait_for.wait()
        logger.debug(f"Running PipelineStage: {self.__class__.__name__}...")
        t = time.perf_counter()
        worker = Worker(input_queue, self.batch_size, strict=self.strict, batch_processor=self.process_items_fn)
        async with asyncio.TaskGroup() as tg:
            for _ in range(self.num_workers):
                tg.create_task(worker(output_queue=output_queue))
        output_queue.shutdown()
        self.finished_event.set()
        logger.info(f"Finished PipelineStage: {self.__class__.__name__} in {time.perf_counter() - t:.2f} seconds")