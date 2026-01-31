from abc import abstractmethod
import asyncio

from spotify_analysis.data.worker import Worker

class AsyncPipelineStage[I, O]:
    batch_size: int
    num_workers: int
    strict: bool
    
    def __init__(self, batch_size: int, num_workers: int, strict: bool):
        super().__init__()
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0")
        if num_workers <= 0:
            raise ValueError("num_workers must be greater than 0")
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.strict = strict
        
    @abstractmethod
    async def _process_item(self, item: I) -> O:
        ...
    
    async def _process_items[I, O](self, items: list[I], output_queue: asyncio.Queue[O]):
        for item in items:
            processed_item = await self._process_item(item)
            await output_queue.put(processed_item)
    
    async def run[I, O](self, input_queue: asyncio.Queue[I], output_queue: asyncio.Queue[O]):
        worker = Worker(input_queue, self.batch_size, strict=self.strict, batch_processor=self._process_items)
        async with asyncio.TaskGroup() as tg:
            for _ in range(self.num_workers):
                tg.create_task(worker(output_queue=output_queue))
        output_queue.shutdown()