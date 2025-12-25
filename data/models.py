from typing import Optional
import datetime

from sqlalchemy import (
    String, Date,
    Table, Column,
    ForeignKey,
)
from sqlalchemy.orm import (
    DeclarativeBase, 
    Mapped, mapped_column,
    relationship
)
from sqlalchemy.ext.associationproxy import association_proxy

class Base(DeclarativeBase):
    pass


track_artist = Table(
    "track_artists",
    Base.metadata,
    Column("track_id", ForeignKey("tracks.track_id"), primary_key=True),
    Column("artist_id", ForeignKey("artists.artist_id"), primary_key=True),
)

track_album = Table(
    "track_albums",
    Base.metadata,
    Column("track_id", ForeignKey("tracks.track_id"), primary_key=True),
    Column("album_id", ForeignKey("albums.album_id"), primary_key=True),
)


class Track(Base):
    __tablename__ = "tracks"
    track_id: Mapped[int] = mapped_column(primary_key=True)
    track_name: Mapped[str] = mapped_column(String(128))
    
    spotify_track_data: Mapped[Optional["SpotifyTrackData"]] = relationship(back_populates="track")
    musicbrainz_track_data: Mapped[Optional["MusicBrainzTrackData"]] = relationship(back_populates="track")
    
    artists: Mapped[list["Artist"]] = relationship(secondary=track_artist, back_populates="tracks")
    albums: Mapped[list["Album"]] = relationship(secondary=track_album, back_populates="tracks")
    
class SpotifyTrackData(Base):
    __tablename__ = "spotify_track_data"
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.track_id"), primary_key=True)
    spotify_track_id: Mapped[str] = mapped_column(String(64))
    
    track: Mapped["Track"] = relationship(back_populates="spotify_track_data")
    
musicbrainz_track_language = Table(
    "musicbrainz_track_languages",
    Base.metadata,
    Column("track_id", ForeignKey("musicbrainz_track_data.track_id"), primary_key=True),
    Column("language_id", ForeignKey("languages.language_id"), primary_key=True),
)
    
class MusicBrainzTrackData(Base):
    __tablename__ = "musicbrainz_track_data"
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.track_id"), primary_key=True)
    musicbrainz_track_id: Mapped[str] = mapped_column(String(64))
    score: Mapped[Optional[int]]
    length: Mapped[Optional[int]]
    first_release_data: Mapped[Optional[datetime.date]] = mapped_column(Date())
    
    languages: Mapped[list["Language"]] = relationship(secondary=musicbrainz_track_language, back_populates="musicbrainz_track_data")
    track: Mapped[Track] = relationship(back_populates="musicbrainz_track_data")
    
class Language(Base):
    __tablename__ = "languages"
    language_id: Mapped[int] = mapped_column(primary_key=True)
    language_name: Mapped[str] = mapped_column(String(32))
    
    musicbrainz_track_data: Mapped[list["MusicBrainzTrackData"]] = relationship(secondary=musicbrainz_track_language, back_populates="languages")
    tracks: Mapped[list[Track]] = association_proxy("musicbrainz_track_data", "track")
    
    
class Artist(Base):
    __tablename__ = "artists"
    artist_id: Mapped[int] = mapped_column(primary_key=True)
    artist_name: Mapped[str] = mapped_column(String(128))
    
    tracks = relationship(secondary=track_artist, back_populates="artists")
    
    musicbrainz_artist_data: Mapped[Optional["MusicBrainzArtistData"]] = relationship(back_populates="artist")
    
class MusicBrainzArtistData(Base):
    __tablename__ = "musicbrainz_artist_data"
    artist_id: Mapped[int] = mapped_column(ForeignKey("artists.artist_id"), primary_key=True)
    musicbrainz_artist_id: Mapped[str] = mapped_column(String(64))
    artist_type: Mapped[Optional[str]]
    country: Mapped[Optional[str]]
    gender: Mapped[Optional[str]]
    
    artist: Mapped[Artist] = relationship(back_populates="musicbrainz_artist_data")
    
class Album(Base):
    __tablename__ = "albums"
    album_id: Mapped[int] = mapped_column(primary_key=True)
    album_name: Mapped[str] = mapped_column(String(128))
    
    tracks = relationship(secondary=track_album, back_populates="albums")