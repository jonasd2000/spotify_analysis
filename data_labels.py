from enum import Enum


class DataLabels(Enum):
    TRACK_NAME = "track_name"
    ARTIST = "artist"
    ALBUM_NAME = "album_name"
    TIMESTAMP = "timestamp"
    DURATION = "duration"
    PLATFORM = "platform"
    COUNTRY = "country"
    IP_ADDRESS = "ip_address"
    TRACK_ID = "track_id"
    PODCAST_NAME = "podcast_name"
    PODCAST_EPISODE_NAME = "podcast_episode_name"
    PODCAST_EPISODE_ID = "podcast_episode_id"
    AUDIOBOOK_TITLE = "audiobook_title"
    AUDIOBOOK_CHAPTER_TITLE = "audiobook_chapter_title"
    AUDIOBOOK_CHAPTER_ID = "audiobook_chapter_id"
    REASON_START = "reason_start"
    REASON_END = "reason_end"
    SHUFFLE = "shuffle"
    SKIPPED = "skipped"
    OFFLINE = "offline"
    OFFLINE_TIMESTAMP = "offline_timestamp"
    INCOGNITO_MODE = "incognito_mode"


SPOTIFY_LABELS = {
    DataLabels.TIMESTAMP: "ts",
    DataLabels.PLATFORM: "platform",
    DataLabels.DURATION: "ms_played",
    DataLabels.COUNTRY: "conn_country",
    DataLabels.IP_ADDRESS: "ip_addr",
    DataLabels.TRACK_NAME: "master_metadata_track_name",
    DataLabels.ARTIST: "master_metadata_album_artist_name",
    DataLabels.ALBUM_NAME: "master_metadata_album_album_name",
    DataLabels.TRACK_ID: "spotify_track_uri",
    DataLabels.PODCAST_EPISODE_NAME: "episode_name",
    DataLabels.PODCAST_NAME: "episode_show_name",
    DataLabels.PODCAST_EPISODE_ID: "spotify_episode_uri",
    DataLabels.AUDIOBOOK_TITLE: "audiobook_title",
    DataLabels.AUDIOBOOK_CHAPTER_ID: "audiobook_chapter_uri",
    DataLabels.AUDIOBOOK_CHAPTER_TITLE: "audiobook_chapter_title",
    DataLabels.REASON_START: "reason_start",
    DataLabels.REASON_END: "reason_end",
    DataLabels.SHUFFLE: "shuffle",
    DataLabels.SKIPPED: "skipped",
    DataLabels.OFFLINE: "offline",
    DataLabels.OFFLINE_TIMESTAMP: "offline_timestamp",
    DataLabels.INCOGNITO_MODE: "incognito_mode",
}
