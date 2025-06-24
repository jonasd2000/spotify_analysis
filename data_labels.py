"""
This module contains constants and functions for working with data labels.

The DataLabels class is used to define standard names for the columns in the streaming data.
The SPOTIFY_LABELS dictionary is used to map the column names in the streaming data to the DataLabels enum.
"""

from enum import Enum
from typing import Any, Dict


class DataLabels(Enum):
    """
    Enum class for defining standard names for the columns in the streaming data.
    """

    TRACK_NAME = "track_name"
    ARTIST = "artist"
    ALBUM_NAME = "album_name"
    TIMESTAMP = "timestamp"
    MILLISECONDS_PLAYED = "milliseconds_played"
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
    MEDIA_TYPE = "media_type"


SPOTIFY_LABELS = {
    DataLabels.TIMESTAMP: "ts",
    DataLabels.PLATFORM: "platform",
    DataLabels.MILLISECONDS_PLAYED: "ms_played",
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


def fill_template(
    template: Dict[DataLabels, Any], labels: Dict[DataLabels, str]
) -> Dict[str, Any]:
    """
    Fill in a template dictionary with values from a labels dictionary.
    Replace the keys in the template with the corresponding values in the labels dictionary.

    Parameters
    ----------
    template : Dict[DataLabels, Any]
        A dictionary with keys from DataLabels and values to be filled in.
    labels : Dict[DataLabels, str]
        A dictionary with keys from DataLabels and values that are the labels to be replaced in the template.

    Returns
    -------
    filled_template : Dict[str, Any]
        The template dictionary with the labels replaced.
    """

    filled_template = {}
    for k, v in template.items():
        filled_template[labels.get(k, k.value)] = v
    return filled_template


def map_labels_to_standard(labels: Dict[DataLabels, str]) -> Dict[str, str]:
    """
    Map a dictionary of labels to standard DataLabels values.
    Replace the values in the labels dictionary with the corresponding DataLabels standard values.

    Parameters
    ----------
    labels : Dict[DataLabels, str]
        A dictionary with keys from DataLabels and values that are the labels to be mapped.

    Returns
    -------
    mapped_labels : Dict[str, str]
        The labels dictionary with the values mapped to the corresponding DataLabels values.
    """
    mapped_labels = {}
    for k, v in labels.items():
        mapped_labels[v] = k.value
    return mapped_labels
