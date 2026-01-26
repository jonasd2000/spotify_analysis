import asyncio
import logging
from typing import Callable, Awaitable


logger = logging.getLogger(__name__)


async def get_batch[T](queue: asyncio.Queue[T], batch_size: int, strict: bool) -> list[T]:
    """
    Helper to pull a batch of items from a queue.

    If strict is True, this function will only return batches of size batch_size.
    If strict is False, this function will return batches of size up to batch_size.
    If the queue is shut down before a batch of size batch_size can be retrieved, this function will return the remaining items that are currently in the queue.
    If the queue is shut down and there are no more items in the queue, this function will raise asyncio.QueueShutDown.

    :param queue: The queue to pull items from.
    :param batch_size: The size of the batch to retrieve.
    :param strict: Whether to require batches of size batch_size or return batches of size up to batch_size.
    :return: A list of items from the queue.
    """
    
    batch = []
    while True:
        if len(batch) == batch_size:
            return batch
        
        try:
            batch.append(await queue.get())
        except asyncio.QueueShutDown: # when the queue is shut down and empty
            if len(batch) == 0: # when the queue is shut down and no items are in the queue, the task is done
                raise
            # when there are still items in the queue, flush them
            return batch
        
        while len(batch) < batch_size and not queue.empty():
            batch.append(queue.get_nowait())
        
        if not strict:
            return batch


class Worker[T]:
    queue: asyncio.Queue[T]
    batch_size: int
    batch_processor: Callable[[list[T]], Awaitable[None]]
    
    def __init__(
        self,
        queue: asyncio.Queue[T],
        batch_size: int,
        strict: bool,
        batch_processor: Callable[[list[T]], Awaitable[None]],
        stop_on_queue_shutdown: bool = True
    ):
        self.queue = queue
        self.batch_size = batch_size
        self.batch_processor = batch_processor
        self.strict = strict
        self.stop_on_queue_shutdown = stop_on_queue_shutdown
    
    async def __call__(self, *args, **kwds):
        while True:
            try:
                batch = await get_batch(self.queue, self.batch_size, strict=self.strict)
            except asyncio.QueueShutDown:
                if self.stop_on_queue_shutdown:
                    logger.debug(f"Queue shut down, stopping worker with processor {self.batch_processor.__name__}")
                    return
                
            await self.batch_processor(batch, *args, **kwds)
            
            for item in batch:
                self.queue.task_done()
                
                
async def queue_splitter[I](batch: list[I], *queues: asyncio.Queue[I]) -> None:
    for item in batch:
        for queue in queues:
            await queue.put(item)