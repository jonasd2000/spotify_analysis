from abc import ABC, abstractmethod
import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, Any

from spotify_analysis.api.spotify import SpotifyClient
from spotify_analysis.api.api_helpers import retry
from spotify_analysis.data.worker import Worker
from spotify_analysis.data.services import SpotifyTracksAPIResponse

logger = logging.getLogger(__name__)


class Getter[I, O](ABC):
    batch_size: int
    num_workers: int
    strict: bool
    
    def __init__(self, batch_size: int = 1, num_workers: int = 1, strict: bool = True):
        super().__init__()
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0")
        if num_workers <= 0:
            raise ValueError("num_workers must be greater than 0")
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.strict = strict
    
    @abstractmethod
    async def _get_items(self, items: list[I], output_queue: asyncio.Queue[O]) -> None:
        ...
    
    async def get_data(self, input_queue: asyncio.Queue[I], output_queue: asyncio.Queue[O]) -> None:
        worker = Worker(input_queue, self.batch_size, strict=self.strict, batch_processor=self._get_items)
        async with asyncio.TaskGroup() as tg:
            for _ in range(self.num_workers):
                tg.create_task(worker(output_queue=output_queue))
        output_queue.shutdown()
        
class NullGetter[I, O](Getter[I, O]):
    async def _get_items(self, items: list[I], output_queue: asyncio.Queue[O]) -> None:
        return
    
class IdentityGetter[I](Getter[I, I]):
    async def _get_items(self, items: list[I], output_queue: asyncio.Queue[I]) -> None:
        for item in items:
            await output_queue.put(item)
    
class APIGetter[I, O](Getter[I, O]):
    credential_fields: Optional[list[str]] = None
    request_retries: Optional[int] = 3


class SpotifyAPICacheGetter(Getter[str, dict[str, Any]]):
    cache_path = Path("spotify_api_cache.json")
    
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

    async def _uri_batch_cache_get(self, uri_batch: list[str], cache_response_queue: asyncio.Queue[dict[str, Any]], uris_needing_api_queue: asyncio.Queue[str]):
        print(f"[Spotify] Filtering {len(uri_batch)} items")
        track_infos_in_cache = await self.get_tracks_by_uris_from_cache(uri_batch)
        uris_in_cache = [track_info["uri"] for track_info in track_infos_in_cache]
        
        remaining_uris = list(set(uri_batch) - set(uris_in_cache))
        
        # append track infos found in cache to track_infos_list
        for track_info in track_infos_in_cache:
            await track_infos_queue.put(track_info)
            
        # put remaining uris into filtered_uris_queue
        for uri in remaining_uris:
            await uris_needing_api_queue.put(uri)
            
class SpotifyAPIGetter(APIGetter[str, SpotifyTracksAPIResponse]):
    credential_fields = ["SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET"]
    request_retries = 3
    
    api_tracks_request_batch_size = 50
    
    spotify_client: SpotifyClient
    
    def __init__(self):
        super().__init__(batch_size=self.api_tracks_request_batch_size, strict=True)
        self.spotify_client = SpotifyClient()
    
    @retry
    async def _uri_batch_api_call(self, uri_batch: list[str], api_response_queue: asyncio.Queue[SpotifyTracksAPIResponse]):
        print(f"[Spotify] Requesting data for {len(uri_batch)} items")
        tracks = await self.spotify_client.tracks(uri_batch)
        api_response_queue.put(tracks)
    
    async def _get_items(self, items: list[str], output_queue: asyncio.Queue[SpotifyTracksAPIResponse]):
        await self._uri_batch_api_call(items, output_queue)
    