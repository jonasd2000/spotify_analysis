import asyncio
from typing import AsyncGenerator, Callable, Awaitable

async def get_batch[T](queue: asyncio.Queue[T], batch_size: int) -> list[T]:
    """Helper to pull a batch from a queue."""
    batch = []
    # Get the first item (blocks until at least one is available)
    batch.append(await queue.get())
    
    # Try to get more items until batch_size is met or queue is empty
    while ((len(batch) < batch_size) if batch_size else True) and not queue.empty():
        batch.append(queue.get_nowait())
    return batch

async def strict_batch_iterator[T](queue: asyncio.Queue[T], batch_size: int, stop_event: asyncio.Event) -> AsyncGenerator[list[T]]:
    """
    Yields batches only when batch_size is reached 
    OR when stop_event is set and queue is empty.
    """
    batch = []
    while not (stop_event.is_set() and queue.empty()):
        try:
            # Wait for an item with a timeout so we can check the stop_event
            item = await asyncio.wait_for(queue.get(), timeout=0.1)
            batch.append(item)
            
            if len(batch) == batch_size:
                yield batch
                batch = []
        except asyncio.TimeoutError:
            continue
            
    # Final flush of remaining items
    if batch:
        yield batch


class Worker[T]:
    queue: asyncio.Queue[T]
    batch_size: int
    batch_processor: Callable[[list[T]], Awaitable[None]]
    
    def __init__(self, queue: asyncio.Queue[T], batch_size: int, batch_processor: Callable[[list[T]], Awaitable[None]]):
        self.queue = queue
        self.batch_size = batch_size
        self.batch_processor = batch_processor
    
class VariableBatchSizeWorker[T](Worker[T]):
    def __init__(self, queue: asyncio.Queue[T], batch_size: int, batch_processor: Callable[[list[T]], Awaitable[None]]):
        super().__init__(queue, batch_size, batch_processor)
        
    async def __call__(self, *args, **kwds):
        while True:
            batch = await get_batch(self.queue, self.batch_size)
            await self.batch_processor(batch, *args, **kwds)
            
            for item in batch:
                self.queue.task_done()
    
class FixedBatchSizeWorker[T](Worker):
    def __init__(self, queue: asyncio.Queue[T], queue_put_finished: asyncio.Event, batch_size: int, batch_processor: Callable[[list[T]], Awaitable[None]]):
        super().__init__(queue, batch_size, batch_processor)
        self.queue_put_finished = queue_put_finished
        
    async def __call__(self, *args, **kwargs):
        async for batch in strict_batch_iterator(self.queue, self.batch_size, self.queue_put_finished):
            await self.batch_processor(batch, *args, **kwargs)
            
            for item in batch:
                self.queue.task_done()