from typing import Optional, Any
import datetime

from sqlalchemy import (
    String, Date,
    Table, Column,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Session as SQLAlchemySession,
    DeclarativeBase, 
    Mapped, mapped_column,
    relationship,
)
from sqlalchemy.ext.associationproxy import association_proxy

class Base(DeclarativeBase):
    pass


track_artist = Table(
    "track_artists",
    Base.metadata,
    Column("track_id", ForeignKey("track.track_id"), primary_key=True),
    Column("artist_id", ForeignKey("artists.artist_id"), primary_key=True),
)

track_album = Table(
    "track_albums",
    Base.metadata,
    Column("track_id", ForeignKey("track.track_id"), primary_key=True),
    Column("album_id", ForeignKey("albums.album_id"), primary_key=True),
)


class Track(Base):
    __tablename__ = "track"
    track_id: Mapped[int] = mapped_column(primary_key=True)
    track_name: Mapped[str] = mapped_column(String(128))
    
    spotify_track_data: Mapped[Optional["SpotifyTrackData"]] = relationship(back_populates="track")
    musicbrainz_track_data: Mapped[Optional["MusicBrainzTrackData"]] = relationship(back_populates="track")
    
    artists: Mapped[list["Artist"]] = relationship(secondary=track_artist, back_populates="tracks")
    albums: Mapped[list["Album"]] = relationship(secondary=track_album, back_populates="tracks")
    
    listening_events: Mapped[list["ListeningEvent"]] = relationship(back_populates="track")
    
class SpotifyTrackData(Base):
    __tablename__ = "spotify_track_data"
    track_id: Mapped[int] = mapped_column(ForeignKey("track.track_id"), primary_key=True)
    spotify_track_id: Mapped[str] = mapped_column(String(64), unique=True)
    
    track: Mapped[Track] = relationship(back_populates="spotify_track_data")
    
musicbrainz_track_language = Table(
    "musicbrainz_track_languages",
    Base.metadata,
    Column("track_id", ForeignKey("musicbrainz_track_data.track_id"), primary_key=True),
    Column("language_id", ForeignKey("languages.language_id"), primary_key=True),
)
    
class MusicBrainzTrackData(Base):
    __tablename__ = "musicbrainz_track_data"
    track_id: Mapped[int] = mapped_column(ForeignKey("track.track_id"), primary_key=True)
    musicbrainz_track_id: Mapped[str] = mapped_column(String(64), unique=True)
    score: Mapped[Optional[int]]
    length: Mapped[Optional[int]]
    first_release_data: Mapped[Optional[datetime.date]] = mapped_column(Date())
    
    languages: Mapped[list["Language"]] = relationship(secondary=musicbrainz_track_language, back_populates="musicbrainz_track_data")
    track: Mapped[Track] = relationship(back_populates="musicbrainz_track_data")
    
class Language(Base):
    __tablename__ = "languages"
    language_id: Mapped[int] = mapped_column(primary_key=True)
    language_name: Mapped[str] = mapped_column(String(32), unique=True)
    
    musicbrainz_track_data: Mapped[list["MusicBrainzTrackData"]] = relationship(secondary=musicbrainz_track_language, back_populates="languages")
    tracks: Mapped[list[Track]] = association_proxy("musicbrainz_track_data", "track")
    
    
class Artist(Base):
    __tablename__ = "artists"
    artist_id: Mapped[int] = mapped_column(primary_key=True)
    artist_name: Mapped[str] = mapped_column(String(128), unique=True)
    
    tracks: Mapped[list["Track"]] = relationship(secondary=track_artist, back_populates="artists")
    
    musicbrainz_artist_data: Mapped[Optional["MusicBrainzArtistData"]] = relationship(back_populates="artist")
    
class MusicBrainzArtistData(Base):
    __tablename__ = "musicbrainz_artist_data"
    artist_id: Mapped[int] = mapped_column(ForeignKey("artists.artist_id"), primary_key=True)
    musicbrainz_artist_id: Mapped[str] = mapped_column(String(64), unique=True)
    artist_type: Mapped[Optional[str]]
    country: Mapped[Optional[str]]
    gender: Mapped[Optional[str]]
    
    artist: Mapped[Artist] = relationship(back_populates="musicbrainz_artist_data")
    
class Album(Base):
    __tablename__ = "albums"
    album_id: Mapped[int] = mapped_column(primary_key=True)
    album_name: Mapped[str] = mapped_column(String(128))
    
    tracks: Mapped[list["Track"]] = relationship(secondary=track_album, back_populates="albums")
    
class Podcast(Base):
    __tablename__ = "podcasts"
    podcast_id: Mapped[int] = mapped_column(primary_key=True)
    podcast_name: Mapped[str] = mapped_column(String(128))
    
    episodes: Mapped[list["PodcastEpisode"]] = relationship(back_populates="podcast")
    
class PodcastEpisode(Base):
    __tablename__ = "podcast_episodes"
    episode_id: Mapped[int] = mapped_column(primary_key=True)
    episode_name: Mapped[str] = mapped_column(String(128))
    podcast_id: Mapped[int] = mapped_column(ForeignKey("podcasts.podcast_id"))
    
    podcast: Mapped["Podcast"] = relationship(back_populates="episodes")
    
    spotify_podcast_episode_data: Mapped[Optional["SpotifyPodcastEpisodeData"]] = relationship(back_populates="episode")
    
    listening_events: Mapped[list["ListeningEvent"]] = relationship(back_populates="podcast_episode")
    
class SpotifyPodcastEpisodeData(Base):
    __tablename__ = "spotify_podcast_episode_data"
    episode_id: Mapped[int] = mapped_column(ForeignKey("podcast_episodes.episode_id"), primary_key=True)
    spotify_episode_id: Mapped[str] = mapped_column(String(64))
    
    episode: Mapped["PodcastEpisode"] = relationship(back_populates="spotify_podcast_episode_data")
    
class Audiobook(Base):
    __tablename__ = "audiobooks"
    audiobook_id: Mapped[int] = mapped_column(primary_key=True)
    audiobook_title: Mapped[str] = mapped_column(String(128))
    
    chapters: Mapped[list["AudiobookChapter"]] = relationship(back_populates="audiobook")
    
class AudiobookChapter(Base):
    __tablename__ = "audiobook_chapters"
    chapter_id: Mapped[int] = mapped_column(primary_key=True)
    chapter_title: Mapped[str] = mapped_column(String(128))
    audiobook_id: Mapped[int] = mapped_column(ForeignKey("audiobooks.audiobook_id"))
    
    audiobook: Mapped["Audiobook"] = relationship(back_populates="chapters")
    
    spotify_audiobook_chapter_data: Mapped[Optional["SpotifyAudiobookChapterData"]] = relationship(back_populates="chapter")
    
    listening_events: Mapped[list["ListeningEvent"]] = relationship(back_populates="audiobook_chapter")
    
class SpotifyAudiobookChapterData(Base):
    __tablename__ = "spotify_audiobook_chapter_data"
    chapter_id: Mapped[int] = mapped_column(ForeignKey("audiobook_chapters.chapter_id"), primary_key=True)
    spotify_chapter_id: Mapped[str] = mapped_column(String(64))
    
    chapter: Mapped["AudiobookChapter"] = relationship(back_populates="spotify_audiobook_chapter_data")
    
    
class ListeningEvent(Base):
    __tablename__ = "listening_events"
    listening_event_id: Mapped[int] = mapped_column(primary_key=True)
    
    track_id: Mapped[Optional[int]] = mapped_column(ForeignKey("track.track_id"))
    podcast_episode_id: Mapped[Optional[int]] = mapped_column(ForeignKey("podcast_episodes.episode_id"))
    audiobook_chapter_id: Mapped[Optional[int]] = mapped_column(ForeignKey("audiobook_chapters.chapter_id"))
    
    timestamp: Mapped[datetime.datetime]
    milliseconds_played: Mapped[int]
    
    __table_args__ = (
        UniqueConstraint("track_id", "timestamp", name="track_timestamp_unique"),
        UniqueConstraint("podcast_episode_id", "timestamp", name="episode_timestamp_unique"),
        UniqueConstraint("audiobook_chapter_id", "timestamp", name="chapter_timestamp_unique"),
    )
    
    track: Mapped[Optional["Track"]] = relationship(back_populates="listening_events")
    podcast_episode: Mapped[Optional["PodcastEpisode"]] = relationship(back_populates="listening_events")
    audiobook_chapter: Mapped[Optional["AudiobookChapter"]] = relationship(back_populates="listening_events")
    
    data: Mapped[Optional["ListeningEventData"]] = relationship(back_populates="listening_event")
    
class ListeningEventData(Base):
    __tablename__ = "listening_event_data"
    listening_event_id: Mapped[int] = mapped_column(ForeignKey("listening_events.listening_event_id"), primary_key=True)
    reason_start: Mapped[Optional[str]] = mapped_column(String(64))
    reason_end: Mapped[Optional[str]] = mapped_column(String(64))
    shuffle: Mapped[bool]
    
    listening_event: Mapped["ListeningEvent"] = relationship(back_populates="data")
    
def get_or_create[T: (Base)](
    session: SQLAlchemySession,
    model: type[T],
    defaults: Optional[dict[str, Any]]=None, 
    **kwargs
) -> tuple[T, bool]:
    """
    Retrieves an instance of `model` from the database session with the given `kwargs`.
    If no instance exists, creates a new instance with the given `kwargs` and `defaults`
    and adds it to the database session.

    Args:
        session (SQLAlchemySession): The database session to use.
        model (type[Base]): The model type to retrieve or create an instance of.
        defaults (Optional[dict[str, Any]], optional): Defaults to use when creating a new instance. Defaults to None.
        **kwargs: Keyword arguments to filter by when retrieving an instance from the database.

    Returns:
        tuple[T, bool]: A tuple containing the instance of `model` and a boolean indicating whether the instance was created or not.
    """
    
    instance = session.query(model).filter_by(**kwargs).one_or_none()
    if instance:
        return instance, False
    else:
        kwargs |= defaults or {}
        instance = model(**kwargs)
        try:
            session.add(instance)
            session.commit()
        except Exception:  # The actual exception depends on the specific database so we catch all exceptions. This is similar to the official documentation: https://docs.sqlalchemy.org/en/latest/orm/session_transaction.html
            session.rollback()
            instance = session.query(model).filter_by(**kwargs).one()
            return instance, False
        else:
            return instance, True
