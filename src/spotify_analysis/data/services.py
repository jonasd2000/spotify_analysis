from typing import TypedDict
from enum import Enum
import io

import polars as pl

from sqlalchemy.ext.asyncio import AsyncEngine

from spotify_analysis.data.data_pipeline.pipelines import DataPipeline
from spotify_analysis.data.data_pipeline.getter import IdentityGetter
from spotify_analysis.data.data_pipeline.parser import SpotifyListeningHistoryParser
from spotify_analysis.data.data_pipeline.transformer import SpotifyListeningHistoryTransformer
from spotify_analysis.data.data_pipeline.loader import SpotifyListeningHistoryLoader
from spotify_analysis.data.data_pipeline.listening_event import SpotifyListeningEventSchema


class Service(Enum):
    SPOTIFY = "spotify"
    
class ServiceNotFoundError(Exception):
    pass
    
def recognise_listening_history_service(file_name: str) -> Service | None:
    if ("Streaming_History_Audio" in file_name):
        return Service.SPOTIFY

    return None


def spotify_listening_history_file_pipeline_factory(db_engine: AsyncEngine) -> DataPipeline[io.BytesIO, io.BytesIO, pl.DataFrame, SpotifyListeningEventSchema]:
    return DataPipeline(
        getter=IdentityGetter[io.BytesIO](),
        parser=SpotifyListeningHistoryParser(),
        transformer=SpotifyListeningHistoryTransformer(),
        loader=SpotifyListeningHistoryLoader(db_engine),
    )
    
    
    
class SpotifyAPISimplifiedArtist(TypedDict):
    """
    Source: https://developer.spotify.com/documentation/web-api/reference/get-track
    """
    external_urls: dict[str, str]
    href: str
    id: str
    name: str
    type: str
    uri: str
    
class SpotifyAPISimplifiedAlbum(TypedDict):
    """
    Source: https://developer.spotify.com/documentation/web-api/reference/get-track
    """
    album_type: str
    total_tracks: int
    available_markets: list[str]
    external_urls: dict[str, str]
    href: str
    id: str
    images: list[dict[str, str]]
    name: str
    release_date: str
    release_date_precision: str
    restrictions: dict[str, str]
    type: str
    uri: str
    artists: list[SpotifyAPISimplifiedArtist]
    
class SpotifyAPITrack(TypedDict):
    """
    Source: https://developer.spotify.com/documentation/web-api/reference/get-track
    """
    album: SpotifyAPISimplifiedAlbum
    artists: list[SpotifyAPISimplifiedArtist]
    available_markets: list[str]
    disc_number: int
    duration_ms: int
    explicit: bool
    external_ids: dict[str, str]
    external_urls: dict[str, str]
    href: str
    id: str
    is_playable: bool
    linked_from: dict[str, str]
    restrictions: dict[str, str]
    name: str
    popularity: int
    preview_url: str
    track_number: int
    type: str
    uri: str
    is_local: bool
    
class SpotifyAPITracks(TypedDict):
    """
    Source: https://developer.spotify.com/documentation/web-api/reference/get-several-tracks
    """
    tracks: list[SpotifyAPITrack]