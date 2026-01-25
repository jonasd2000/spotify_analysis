from abc import ABC, abstractmethod
import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, Any

from spotify_analysis.api.spotify import SpotifyClient
from spotify_analysis.api.api_helpers import retry
from spotify_analysis.data.worker import Worker


logger = logging.getLogger(__name__)


class Getter[I, O](ABC):
    @abstractmethod
    async def get_data(self, input_queue: asyncio.Queue[I], output_queue: asyncio.Queue[O]) -> None:
        ...
        
class NullGetter(Getter):
    async def get_data(self, input_queue: asyncio.Queue, output_queue: asyncio.Queue) -> None:
        return
    
class IdentityGetter[I, O](Getter[I, O]):
    async def get_data(self, input_queue: asyncio.Queue[I], output_queue: asyncio.Queue[O]) -> None:
        while not input_queue.empty():
            item = await input_queue.get()
            await output_queue.put(item)
    
class APIGetter[I, O](Getter[I, O]):
    credential_fields: Optional[list[str]] = None
    request_retries: Optional[int] = 3

class SpotifyAPIGetter(APIGetter):
    credential_fields = ["SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET"]
    request_retries = 3
    
    api_tracks_request_batch_size = 50
    cache_path = Path("spotify_api_cache.json")
    
    spotify_client: SpotifyClient
    
    def __init__(self):
        super().__init__()
        self.spotify_client = SpotifyClient()
    
    @retry
    async def get_tracks_by_uris_from_api(self, track_uris: list[str]) -> list[dict[str, Any]]:
        response = await self.spotify_client.tracks(track_uris)
        if response.status_code != 200:
            raise Exception(f"Spotify API request failed with status code {response.status_code}")
        track_infos = response.json()["tracks"]
        return track_infos
    
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
    
    async def _uri_batch_api_call(self, uri_batch: list[str], track_infos_queue: asyncio.Queue[dict[str, Any]]):
        print(f"[Spotify] Requesting data for {len(uri_batch)} items")
        track_infos = await self.get_tracks_by_uris_from_api(uri_batch)
        for track_info in track_infos:
            track_infos_queue.put(track_info)
    
    async def _uri_batch_filter_call(self, uri_batch: list[str], track_infos_queue: asyncio.Queue[dict[str, Any]], uris_needing_api_queue: asyncio.Queue[str]):
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
            
    async def get_tracks_by_uris(self, track_uri_queue: asyncio.Queue[str], track_infos_queue: asyncio.Queue[dict[str, Any]]) -> None:
        uris_needing_api_queue = asyncio.Queue()
        
        filter_uris_worker = Worker(
            queue=track_uri_queue,
            batch_size=10_000,
            strict=False,
            batch_processor=self._uri_batch_filter_call
        )
        spotify_api_worker = Worker(
            queue=uris_needing_api_queue,
            batch_size=self.api_tracks_request_batch_size,
            strict=True,
            batch_processor=self._uri_batch_api_call,
        )
        filter_task = asyncio.create_task(filter_uris_worker(track_infos_queue=track_infos_queue, uris_needing_api_queue=uris_needing_api_queue))
        api_task = asyncio.create_task(spotify_api_worker(track_infos_queue=track_infos_queue))
        
        await filter_task
        print("Filtering URIs Complete.")
        uris_needing_api_queue.shutdown()
        
        await api_task
        print("Spotify API Requests Complete.")
        track_infos_queue.shutdown()
    
    async def get_data(self, input_queue: asyncio.Queue[str], output_queue: asyncio.Queue[dict[str, Any]]) -> None:
        await self.get_tracks_by_uris(input_queue, output_queue)