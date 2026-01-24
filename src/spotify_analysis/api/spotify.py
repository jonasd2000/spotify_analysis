import datetime
from dataclasses import dataclass, field
import httpx
from pathlib import Path
import logging
from typing import Any, Optional, Callable, Self
import os
import json



logger = logging.getLogger(__name__)


@dataclass
class SpotifyAccessToken:
    data: dict[str, Any]
    _created_at: datetime.datetime = field(init=False)
    _expires_at: datetime.datetime = field(init=False)
    
    def __post_init__(self):
        self._created_at = datetime.datetime.now()
        self.expires_at = self._created_at + datetime.timedelta(seconds=self.expires_in)
    
    @classmethod
    def from_cache(cls: type[Self], cache: dict[str, Any]):
        expires_at = cache.pop("expires_at")
        
        access_token = cls(data=cache)
        access_token._expires_at = datetime.datetime.fromtimestamp(expires_at)
        
        return access_token
    
    def as_header(self):
        token_type = self.data["token_type"]
        access_token = self.data["access_token"]
        return f"{token_type} {access_token}"
    
    def as_cache(self):
        return {
            "token_type": self.data["token_type"],
            "access_token": self.data["access_token"],
            "expires_in": self.expires_in,
            "expires_at": self.expires_at.timestamp(),
        }
    
    @property
    def expires_in(self):
        return self.data["expires_in"]
    
    @property
    def is_expired(self):
        return datetime.datetime.now() > self.expires_at

class SpotifyClient:
    client_credentials: dict[str, str]
    token_cache = Path("spotify_token_cache.json")
    access_token: Optional[SpotifyAccessToken]
    
    def __init__(self, client_id: str=None, client_secret: str=None):
        client_id = client_id or os.getenv("SPOTIPY_CLIENT_ID")
        if client_id is None:
            raise Exception("SPOTIPY_CLIENT_ID is not set")
        client_secret = client_secret or os.getenv("SPOTIPY_CLIENT_SECRET")
        if client_secret is None:
            raise Exception("SPOTIPY_CLIENT_SECRET is not set")
        
        self.client_credentials = {
            "client_id": client_id,
            "client_secret": client_secret,
        }
        self.access_token = None
    
    async def request_access_token(self) -> SpotifyAccessToken:
        endpoint = "https://accounts.spotify.com/api/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_credentials["client_id"],
            "client_secret": self.client_credentials["client_secret"],
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(endpoint, headers=headers, data=data)
        
        access_token = SpotifyAccessToken(data=response.json())
        return access_token
        
    async def get_access_token(self) -> SpotifyAccessToken:
        if self.token_cache.exists():
            with self.token_cache.open("r") as f:
                cache = json.load(f)
                access_token = SpotifyAccessToken.from_cache(cache)
                if not access_token.is_expired:
                    logger.debug("Using cached access token...")
                    return access_token
        
        logger.debug("Requesting new access token...")
        access_token = await self.request_access_token()
        with self.token_cache.open("w") as f:
            json.dump(access_token.as_cache(), f)
        
        return access_token
        
    def async_with_access_token[T](fn: Callable[[], T]) -> Callable[[], T]:
        async def wrapper(self: Self, *args, **kwargs):
            if (self.access_token is None) or self.access_token.is_expired:
                self.access_token = await self.get_access_token()
            return await fn(self, *args, **kwargs)
        return wrapper
        
    @async_with_access_token
    async def get(self, endpoint: str, headers: Optional[dict[str, str]]=None) -> httpx.Response:
        headers = headers or {}
        headers.update({"Authorization": self.access_token.as_header()})
        async with httpx.AsyncClient() as client:
            response = await client.get(endpoint, headers=headers)
        return response