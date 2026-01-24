from abc import ABC, abstractmethod
import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, Any

from spotify_analysis.api.spotify import SpotifyClient
from spotify_analysis.api.api_helpers import retry
from spotify_analysis.data.queue_batchers import FixedBatchSizeWorker, VariableBatchSizeWorker


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
    
    async def _uri_batch_api_call(self, uri_batch: list[str], track_infos_list: list[dict[str, Any]], isrc_queue: asyncio.Queue[str]):
        print(f"[Spotify] Requesting data for {len(uri_batch)} items")
        track_infos = await self.get_tracks_by_uris_from_api(uri_batch)
        for track_info in track_infos:
            track_infos_list.append(track_info)
            isrc = track_info["external_ids"].get("isrc")
            if isrc is not None:
                await isrc_queue.put(isrc)
    
    async def _uri_batch_filter_call(self, uri_batch: list[str], track_infos_list: list[dict[str, Any]], uris_needing_api_queue: asyncio.Queue[str]):
        print(f"[Spotify] Filtering {len(uri_batch)} items")
        track_infos_in_cache = await self.get_tracks_by_uris_from_cache(uri_batch)
        uris_in_cache = [track_info["uri"] for track_info in track_infos_in_cache]
        
        remaining_uris = list(set(uri_batch) - set(uris_in_cache))
        
        # append track infos found in cache to track_infos_list
        track_infos_list.extend(track_infos_in_cache)
            
        # put remaining uris into filtered_uris_queue
        for uri in remaining_uris:
            await uris_needing_api_queue.put(uri)
            
    async def simulate_api_call(self, uri_batch: list[str], track_infos_list: list[dict[str, Any]], isrc_queue: asyncio.Queue[str]):
        print(f"[Spotify] Simulating API call for {len(uri_batch)} items")
        await asyncio.sleep(10)
            
    async def get_tracks_by_uris(self, track_uris: asyncio.Queue[str]) -> list[dict[str, Any]]:
        track_infos = []
        uris_needing_api_queue = asyncio.Queue()
        finished_filtering_uris = asyncio.Event()
        
        
        filter_uris_worker = VariableBatchSizeWorker(
            queue=track_uris,
            batch_size=None,
            batch_processor=self._uri_batch_filter_call
        )
        spotify_api_worker = FixedBatchSizeWorker(
            queue=uris_needing_api_queue,
            queue_put_finished=finished_filtering_uris,
            batch_size=self.api_tracks_request_batch_size,
            batch_processor=self._uri_batch_api_call,
        )
        filter_uris_task = asyncio.create_task(filter_uris_worker(track_infos_list=track_infos, uris_needing_api_queue=uris_needing_api_queue))
        asyncio.create_task(spotify_api_worker(track_infos_list=track_infos, isrc_queue=self.isrc_queue))
        
        await self.file_upload_finished.wait()
        
        await track_uris.join()
        finished_filtering_uris.set()
        filter_uris_task.cancel()
        print("Filtering URIs Complete.")
        
        await uris_needing_api_queue.join()
        print("Spotify API Requests Complete.")
        
        return track_infos
    
    async def get_data(self) -> list[dict[str, Any]]:
        tracks_info = await self.get_tracks_by_uris(self.uri_queue)
        return tracks_info