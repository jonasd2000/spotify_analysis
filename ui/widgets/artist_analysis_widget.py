from itertools import zip_longest

import humanize
import polars as pl
from nicegui import ui

from data_labels import DataLabels

from .plots import Plot
from .list import LabelList
from .widget import DataWidget
from .events import EventType


class ArtistOverTimePlot(Plot):
    def on_event(self, event_type, *args, **kwargs):
        super().on_event(event_type, *args, **kwargs)
        match event_type:
            case EventType.ARTIST_SELECTED:
                self.update()
            case _:
                pass

class ArtistTopSongsList(LabelList):
    def on_event(self, event_type, *args, **kwargs):
        super().on_event(event_type, *args, **kwargs)
        match event_type:
            case EventType.DATA_ADDED:
                self.update()
            case EventType.ARTIST_SELECTED:
                self.update()
            case _:
                pass


class ArtistAnalysisWidget(DataWidget):
    """
    Widget for artist analysis.
    """

    artist_over_time_plot: Plot
    artist_top_five: LabelList

    def __init__(self, data_manager, parent=None):
        super().__init__(data_manager, parent)

        # artist over time plot initialisation
        self.artist_over_time_plot = ArtistOverTimePlot(
            trace=(self.create_artist_over_time_trace, {}),
            layout={
                "plot_bgcolor": "#E5ECF6",
                "xaxis": {"fixedrange": True},
                "yaxis": {
                    "fixedrange": True,
                    "gridcolor": "white",
                    "title": {"text": "Hours Played"},
                },
            },
            config={
                "responsive": True,
                "displayModeBar": False,
            },
            parent=self,
        )
        self.artist_top_five = ArtistTopSongsList(
            length=5,
            text=(self.get_artist_top_songs_labels, {}),
            parent=self,
        )

    def get_artist_names(self):
        if self.data_manager.streaming_data.is_empty():
            return []
        return (
            self.data_manager.streaming_data[DataLabels.ARTIST.value]
            .drop_nulls()
            .unique()
            .to_list()
        )

    def on_event(self, event_type: EventType, *args, **kwargs):
        match event_type:
            case EventType.DATA_ADDED:
                self.on_data_change()
            case _:
                pass

    def on_data_change(self):
        """
        Called when the 'data_change' event is received.
        """
        self.artist_select.set_options(self.get_artist_names())

    def on_artist_change(self, select_artist: str) -> str:
        """
        Called when the artist_select widget is changed.
        Sets the value of self.selected_artist.
        """
        self.emit_event(EventType.ARTIST_SELECTED, propagate_upwards=False, artist=select_artist)
        return select_artist

    def create_artist_over_time_trace(self):
        """
        Generates a chart trace for the hours played of the selected artist over time.

        Parameters
        ----------
        None

        Returns
        -------
        Dict
            A dictionary representing the chart trace.
        """
        if self.data_manager.streaming_data.is_empty():
            return None

        selected_artist = self.artist_select.value
        if selected_artist is None:
            return {}

        # time dataframe
        # a dataframe which contains all year month combinations from the date range of the streaming data
        min_date = self.data_manager.streaming_data[DataLabels.TIMESTAMP.value].min()
        max_date = self.data_manager.streaming_data[DataLabels.TIMESTAMP.value].max()
        time_df = (
            pl.DataFrame(
                {
                    "date": pl.date_range(  # generate date range from min_date to max_date
                        start=min_date,
                        end=max_date,
                        interval="1mo",
                        closed="both",
                        eager=True,
                    ),
                }
            )
            .with_columns(  # add year and month columns
                pl.col("date").dt.year().alias("year"),
                pl.col("date").dt.month().alias("month"),
            )
            .drop("date")  # drop date column
        )

        # group the data for the selected artist by year and month
        # and sum the milliseconds played
        data = (
            self.data_manager.streaming_data.filter(
                pl.col(DataLabels.ARTIST.value) == selected_artist
            )
            .group_by(
                pl.col(DataLabels.TIMESTAMP.value).dt.year().alias("year"),
                pl.col(DataLabels.TIMESTAMP.value).dt.month().alias("month"),
            )
            .agg(pl.sum(DataLabels.MILLISECONDS_PLAYED.value))
            .sort("year", "month")
        )

        # join the timeseries dataframe with the data dataframe
        # and fill null values with 0
        # i.e. if there is no data for a month in the date range, the value for that month will be 0
        data = (
            time_df.join(data, on=["year", "month"], how="left")
            .fill_null(0)
            .with_columns(
                pl.date(pl.col("year"), pl.col("month"), pl.lit(1)).alias("date"),
            )
        )

        return {
            "x": data["date"].to_list(),
            "y": (data[DataLabels.MILLISECONDS_PLAYED.value] / 3600000).to_list(),
            "type": "bar",
            # "mode": "lines",
            "name": selected_artist,
        }

    def get_artist_top_songs_labels(self):
        """
        Updates the top five labels for the selected artist with the most played tracks.

        If the data manager has no data, it will clear the labels.

        Otherwise, it will group the data by track name and artist, sum the milliseconds played,
        sort the data by the sum of milliseconds played in descending order,
        limit it to the top five tracks, and then update the labels with the track name and play time.
        """
        
        if self.data_manager.streaming_data.is_empty():
            return ["" for _ in range(len(self.artist_top_five))]

        selected_artist = self.artist_select.value

        # filter the data for the selected artist
        # group it by track name and artist
        # and sum the milliseconds played
        # then sort the data by the sum of milliseconds played in descending order
        data = (
            self.data_manager.streaming_data.filter(
                pl.col(DataLabels.ARTIST.value) == selected_artist
            )
            .group_by(
                DataLabels.TRACK_NAME.value,
                DataLabels.ARTIST.value,
            )
            .agg(pl.sum(DataLabels.MILLISECONDS_PLAYED.value))
            .sort(DataLabels.MILLISECONDS_PLAYED.value, descending=True)
            .with_columns(  # convert milliseconds to human readable time
                pl.duration(
                    milliseconds=pl.col(DataLabels.MILLISECONDS_PLAYED.value)
                ).alias("duration")
            )
            .limit(len(self.artist_top_five))
        )
        
        return [f"{i + 1}. {row[DataLabels.TRACK_NAME.value]} ({humanize.precisedelta(row['duration'], format='%0.0f')})" for i, row in enumerate(data.iter_rows(named=True))]

    def create_widget(self, *args, **kwargs):
        with ui.column() as widget:
            self.artist_select = ui.select(
                self.get_artist_names(),
                label="Artist",
                with_input=True,
                on_change=self.on_artist_change,
            )
            with ui.grid(rows=1, columns=r"100%").classes("w-dvw"):
                self.artist_over_time_plot.create_widget()
                self.artist_top_five.create_widget()
        return widget
