from abc import ABC, abstractmethod
import json
import logging
from pathlib import Path
from typing import Optional, Any

from spotify_analysis.data.api_helpers import retry


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
    
    @retry
    async def get_tracks_by_uris_from_api(self, track_uris: list[str]) -> list[dict[str, Any]]:
        raise NotImplementedError
    
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
    
    async def get_tracks_by_uris(self, track_uris: list[str]) -> list[dict[str, Any]]:
        tracks_info_from_cache = await self.get_tracks_by_uris_from_cache(track_uris)
        track_uris_in_cache = [track_info["uri"] for track_info in tracks_info_from_cache]
        
        remaining_track_uris = list(set(track_uris) - set(track_uris_in_cache))
        
        batch_size = self.api_tracks_request_batch_size
        remaining_track_uris_batches = [
            remaining_track_uris[i:i + batch_size] 
            for i in range(0, len(remaining_track_uris), batch_size)
        ]
        
        tracks_info_from_api = []
        
        for track_uris_batch in remaining_track_uris_batches:
            track_info_batch = await self.get_tracks_by_uris_from_api(track_uris_batch, self.api_request_retries)
            tracks_info_from_api.extend(track_info_batch)
        
        tracks_info = tracks_info_from_cache + tracks_info_from_api
        return tracks_info
    
    async def get_data(self) -> list[dict[str, Any]]:
        tracks_info = await self.get_tracks_by_uris(self.track_uris)
        return tracks_info