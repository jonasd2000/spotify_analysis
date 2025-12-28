from abc import ABC, abstractmethod

from sqlalchemy.orm import Session as SQLAlchemySession

from .listening_event import ListeningEventSchema, TrackType, SpotifyListeningEventSchema
from .models import (
    Track, SpotifyTrackData, Album, Artist,
    PodcastEpisode, SpotifyPodcastEpisodeData, Podcast,
    AudiobookChapter, SpotifyAudiobookChapterData, Audiobook,
    ListeningEvent, ListeningEventData,
)


class Loader(ABC):
    url: str
        
    @abstractmethod
    def insert_listening_event(self, session: SQLAlchemySession, listening_event_schema: ListeningEventSchema) -> None:
        pass
    
class SpotifyLoader(Loader):
    def create_track(self, listening_event_schema: SpotifyListeningEventSchema):
        artists = [
            Artist(
                artist_name=artist_name,
            )
            for artist_name in listening_event_schema.creators
        ]
        album = Album(
            album_name=listening_event_schema.collection_name,
        )
        track = Track(
            track_name=listening_event_schema.track_name,
            spotify_track_data=SpotifyTrackData(
                spotify_track_id=listening_event_schema.spotify_track_id
            ),
            artists=artists,
        )
        track.albums.append(album)
        
        return track
    
    def insert_listening_event(self, session: SQLAlchemySession, listening_event_schema: SpotifyListeningEventSchema) -> None:
        listening_event = ListeningEvent(
            timestamp=listening_event_schema.timestamp,
            milliseconds_played=listening_event_schema.ms_played,
        )
        match listening_event_schema.track_type:
            case TrackType.SONG:
                track = self.create_track(listening_event_schema)
                listening_event.track = track
            case TrackType.PODCAST_EPISODE:
                episode = self.create_podcast_episode(listening_event_schema)
                listening_event.podcast_episode = episode
            case TrackType.AUDIOBOOK_CHAPTER:
                chapter = self.create_audiobook_chapter(listening_event_schema)
                listening_event.audiobook_chapter = chapter
                
        listening_event.data = ListeningEventData(
            reason_start=listening_event_schema.reason_start,
            reason_end=listening_event_schema.reason_end,
            shuffle=listening_event_schema.shuffle,
        )
        
        session.add(listening_event)
        session.commit()