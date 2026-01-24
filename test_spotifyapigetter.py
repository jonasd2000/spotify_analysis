import asyncio
import sqlite3
from dotenv import load_dotenv

from spotify_analysis.data.data_pipeline.getter import SpotifyAPIGetter


load_dotenv()


async def uploader(queue: asyncio.Queue[str], uris: list[str]) -> None:
    for uri in uris:
        await queue.put(uri)
        await asyncio.sleep(.1)
        print(f"Uploaded {uri}")

async def main() -> None:
    conn = sqlite3.connect("listening_history.db")
    uris = conn.execute("SELECT spotify_uri FROM spotify_track_data").fetchmany(145)
    uris = [uri[0] for uri in uris]
    
    uris_from_file_queue = asyncio.Queue()
    isrc_queue = asyncio.Queue()
    file_upload_finished = asyncio.Event()
    api_finished_event = asyncio.Event()
    
    getter = SpotifyAPIGetter(
        uris_from_file_queue=uris_from_file_queue,
        isrc_queue=isrc_queue,
        file_upload_finished=file_upload_finished
    )
    
    uploader_task = asyncio.create_task(uploader(uris_from_file_queue, uris))
    api_task = asyncio.create_task(getter.get_data())
    
    await uploader_task
    file_upload_finished.set()
    print("Upload Complete.")
    # await api_finished_event.wait()
    api_responses = await api_task
    
    while not isrc_queue.empty():
        isrc = await isrc_queue.get()
        print(isrc)
    
if __name__ == "__main__":
    asyncio.run(main())