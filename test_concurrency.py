import asyncio
import random
from typing import AsyncGenerator

# Constants
URI_COUNT = 100
SPOTIFY_BATCH_SIZE = 10
MB_BATCH_SIZE = 28

async def get_batch[T](queue: asyncio.Queue[T], batch_size: int) -> list[T]:
    """Helper to pull a batch from a queue."""
    batch = []
    # Get the first item (blocks until at least one is available)
    batch.append(await queue.get())
    
    # Try to get more items until batch_size is met or queue is empty
    while len(batch) < batch_size and not queue.empty():
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


async def file_uploader(uri_queue: asyncio.Queue[str]):
    for i in range(URI_COUNT):
        await asyncio.sleep(random.uniform(0, 0.1))
        uri = f"file:track:{i}"
        await uri_queue.put(uri)
        # print(f"Uploaded: {uri}")

async def spotify_worker(uri_queue: asyncio.Queue[str], isrc_queue: asyncio.Queue[str], upload_finished: asyncio.Event):
    async for uri_batch in strict_batch_iterator(uri_queue, SPOTIFY_BATCH_SIZE, upload_finished):
        print(f"[Spotify] Requesting data for {len(uri_batch)} items")
        
        # Simulate the expensive API call
        await asyncio.sleep(random.uniform(0.5, 1.0))
        
        for uri in uri_batch:
            isrc = f"isrc:{uri.split(':')[-1]}"
            await isrc_queue.put(isrc)
            uri_queue.task_done()

async def musicbrainz_worker(isrc_queue: asyncio.Queue[str], upload_finished: asyncio.Event):
    async for isrc_batch in strict_batch_iterator(isrc_queue, MB_BATCH_SIZE, upload_finished):
        print(f"[MusicBrainz] Requesting data for {len(isrc_batch)} items")
        
        # Simulate the expensive API call
        await asyncio.sleep(random.uniform(1.0, 1.5))
        
        for _ in isrc_batch:
            isrc_queue.task_done()

async def main():
    spotify_uris = asyncio.Queue()
    isrcs = asyncio.Queue()
    file_upload_finished = asyncio.Event()
    spotify_api_requests_finished = asyncio.Event()

    # 1. Start the uploader
    uploader_task = asyncio.create_task(file_uploader(spotify_uris))

    # 2. Start workers (you can scale these up by creating more tasks)
    sp_worker = asyncio.create_task(spotify_worker(spotify_uris, isrcs, file_upload_finished))
    mb_worker = asyncio.create_task(musicbrainz_worker(isrcs, spotify_api_requests_finished))

    # 3. Wait for the uploader to finish sending all files
    await uploader_task
    file_upload_finished.set()
    print("Upload Complete.")

    # 4. Wait for all items in the queues to be processed (task_done() calls)
    await spotify_uris.join()
    spotify_api_requests_finished.set()
    print("Spotify API Requests Complete.")
    await isrcs.join()

    # # 5. Cancel workers (they are in infinite loops)
    # sp_worker.cancel()
    # mb_worker.cancel()
    
    print("Pipeline Complete.")

if __name__ == "__main__":
    asyncio.run(main())