import asyncio
import sqlite3
from dotenv import load_dotenv

from spotify_analysis.data.data_pipeline.getter import SpotifyAPIGetter


load_dotenv()


async def uploader(queue: asyncio.Queue[str], uris: list[str]) -> None:
    for uri in uris:
        await queue.put(uri)
        await asyncio.sleep(.01)
        print(f"Uploaded {uri}")
    queue.shutdown()

async def main() -> None:
    conn = sqlite3.connect("listening_history.db")
    uris = conn.execute("SELECT spotify_uri FROM spotify_track_data").fetchmany(145)
    uris = [uri[0] for uri in uris]
    
    uris_from_file_queue = asyncio.Queue()
    track_info_queue = asyncio.Queue()
    
    getter = SpotifyAPIGetter()
    
    uploader_task = asyncio.create_task(uploader(uris_from_file_queue, uris))
    sp_getter_task = asyncio.create_task(getter.get_data(uris_from_file_queue, track_info_queue))
    
    await uploader_task
    print("Upload Complete.")
    # await api_finished_event.wait()
    await sp_getter_task
    
    print(track_info_queue.qsize())
    
if __name__ == "__main__":
    asyncio.run(main())