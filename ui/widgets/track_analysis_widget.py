from typing import Dict

import humanize
import polars as pl
from nicegui import ui

from data_labels import DataLabels

from .plots import Plot
from .widget import DataWidget
from .events import EventType


class TrackOverTimePlot(Plot):
    def on_event(self, event_type, *args, **kwargs):
        super().on_event(event_type, *args, **kwargs)
        match event_type:
            case EventType.TRACK_SELECTED:
                self.update()
            case _:
                pass

class TrackAnalysisWidget(DataWidget):
    """
    Widget for track analysis.
    """

    track_over_time_plot: Plot

    def __init__(self, data_manager, parent=None):
        super().__init__(data_manager, parent)

        # track over time plot initialisation
        self.track_over_time_plot = TrackOverTimePlot(
            trace=(self.create_track_over_time_trace, {}),
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

    def on_event(self, event_type: EventType, *args, **kwargs):
        match event_type:
            case EventType.DATA_ADDED:
                self.on_data_change()
            case _:
                pass

    def on_data_change(self):
        """
        Called when the 'data_change' event is received.
        Resets the track select widget, the top five tracks labels, and updates the track over time plot.
        """
        self.track_select.set_options(self.get_track_names())

    def get_track_names(self) -> Dict[str, str]:
        if self.data_manager.has_listening_history_data():
            return {}
        return dict(
            self.data_manager.streaming_data.select(DataLabels.TRACK_NAME.value, DataLabels.ARTIST.value)
            .drop_nulls()
            .unique()
            .with_columns((pl.col(DataLabels.TRACK_NAME.value) + " - " + pl.col(DataLabels.ARTIST.value)).alias("label"))
            .select(DataLabels.TRACK_NAME.value, "label")
            .iter_rows()
        )

    def on_track_change(self, select_track: str) -> str:
        """
        Called when the track_select widget is changed.
        Sets the value of self.selected_track.
        """
        self.emit_event(EventType.TRACK_SELECTED, propagate_upwards=False, track=select_track)
        return select_track

    def create_track_over_time_trace(self):
        """
        Generates a chart trace for the hours played of the selected track over time.

        Parameters
        ----------
        None

        Returns
        -------
        Dict
            A dictionary representing the chart trace.
        """
        if self.data_manager.has_listening_history_data():
            return None

        selected_track = self.track_select.value
        if selected_track is None:
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

        # group the data for the selected track by year and month
        # and sum the milliseconds played
        data = (
            self.data_manager.streaming_data.filter(
                pl.col(DataLabels.TRACK_NAME.value) == selected_track
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
            "name": selected_track,
        }

    def create_widget(self, *args, **kwargs):
        with ui.column() as widget:
            self.track_select = ui.select(
                self.get_track_names(),
                label="Track",
                with_input=True,
                on_change=self.on_track_change,
            )
            with ui.grid(rows=1, columns=r"100%").classes("w-dvw"):
                self.track_over_time_plot.create_widget()
        return widget
