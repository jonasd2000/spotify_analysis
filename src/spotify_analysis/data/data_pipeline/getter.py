from abc import ABC, abstractmethod
import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, Any

from spotify_analysis.api.spotify import SpotifyClient
from spotify_analysis.api.api_helpers import retry
from spotify_analysis.data.queue_batchers import strict_batch_iterator


logger = logging.getLogger(__name__)


class Getter[T](ABC):
    @abstractmethod
    async def get_data(self) -> T:
        ...
        
class NullGetter(Getter[None]):
    async def get_data(self) -> None:
        return None
    
class IdentityGetter[T](Getter[T]):
    def __init__(self, data: T):
        self.data = data
        
    async def get_data(self) -> T:
        return self.data
    
class APIGetter[T](Getter[T]):
    credential_fields: Optional[list[str]] = None
    request_retries: Optional[int] = 3    

class SpotifyAPIGetter(APIGetter):
    credential_fields = ["SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET"]
    request_retries = 3
    
    api_tracks_request_batch_size = 50
    cache_path = Path("spotify_api_cache.json")
    
    spotify_client: SpotifyClient
    
    def __init__(self, uris_from_file_queue: asyncio.Queue[str], isrc_queue: asyncio.Queue[str], file_upload_finished: asyncio.Event):
        super().__init__()
        self.spotify_client = SpotifyClient()
        self.uri_queue = uris_from_file_queue
        self.isrc_queue = isrc_queue
        self.file_upload_finished = file_upload_finished
    
    @retry
    async def get_tracks_by_uris_from_api(self, track_uris: list[str]) -> list[dict[str, Any]]:
        return self.spotify_client.tracks(track_uris)
    
    async def get_tracks_by_uris_from_cache(self, track_uris: list[str]) -> list[dict[str, Any]]:
        logger.debug(f"Getting tracks info from cache for {len(track_uris)} tracks...")
        if not self.cache_path.exists():
            return []
        
        with self.cache_path.open("r") as f:
            uri_track_info_map = json.load(f)
        
        tracks_info = [
            uri_track_info_map[uri]
            for uri in track_uris
            if uri in uri_track_info_map
        ]
        
        logger.debug(f"Found {len(tracks_info)}/{len(track_uris)} tracks in cache...")
        
        return tracks_info
    
    async def spotify_api_worker(self, uri_queue: asyncio.Queue[str], isrc_queue: asyncio.Queue[str], track_infos_list: list[dict[str, Any]], finished_event: asyncio.Event):
        async for uri_batch in strict_batch_iterator(uri_queue, self.api_tracks_request_batch_size, finished_event):
            logger.debug(f"[Spotify] Requesting data for {len(uri_batch)} items")
            
            # Simulate the expensive API call
            track_infos = await self.get_tracks_by_uris_from_api(uri_batch)
            
            for track_info in track_infos:
                track_infos_list.append(track_info)
                isrc = track_info["isrc"]
                await isrc_queue.put(isrc)
                uri_queue.task_done()
    
    async def filter_uris_worker(self, uris_from_file_queue: asyncio.Queue[str], uris_needing_api_queue: asyncio.Queue[str], track_infos_list: list[dict[str, Any]], finished_event: asyncio.Event):
        async for uri_batch in strict_batch_iterator(uris_from_file_queue, self.api_tracks_request_batch_size, finished_event):
            print(f"[Spotify] Filtering {len(uri_batch)} items")
            track_infos_in_cache = await self.get_tracks_by_uris_from_cache(uri_batch)
            uris_in_cache = [track_info["uri"] for track_info in track_infos_in_cache]
            
            remaining_uris = list(set(uri_batch) - set(uris_in_cache))
            
            # append track infos found in cache to track_infos_list and mark them as done
            for track_info in track_infos_list:
                track_infos_list.append(track_info)
                uris_from_file_queue.task_done()
                
            # put remaining uris into filtered_uris_queue
            for uri in remaining_uris:
                await uris_needing_api_queue.put(uri)
    
    async def get_tracks_by_uris(self, track_uris: asyncio.Queue[str]) -> list[dict[str, Any]]:
        track_infos = []
        uris_needing_api_queue = asyncio.Queue()
        finished_filtering_uris = asyncio.Event()
        asyncio.create_task(self.filter_uris_worker(
            uris_from_file_queue=track_uris,
            uris_needing_api_queue=uris_needing_api_queue, 
            track_infos_list=track_infos, 
            finished_event=self.file_upload_finished
        ))
        asyncio.create_task(self.spotify_api_worker(
            uri_queue=uris_needing_api_queue,
            isrc_queue=self.isrc_queue, 
            track_infos_list=track_infos,
            finished_event=finished_filtering_uris
        ))
        
        await uris_needing_api_queue.join()
        finished_filtering_uris.set()
        
        return track_infos
    
    async def get_data(self) -> list[dict[str, Any]]:
        tracks_info = await self.get_tracks_by_uris(self.uri_queue)
        return tracks_info