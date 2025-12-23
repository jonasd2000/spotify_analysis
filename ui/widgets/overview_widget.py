import datetime
from typing import Dict

import humanize
import polars as pl
from nicegui import element, ui

from data_labels import DataLabels

from .plots import PlotCollection
from .widget import DataWidget, Widget
from .events import EventType


class OverviewWidget(DataWidget):
    plots: PlotCollection
    date_range: Dict[str, datetime.date]

    def __init__(self, data_manager, parent=None):
        super().__init__(data_manager, parent)
        data_min_date, data_max_date = self.data_manager.get_min_max_date()
        self.date_range = {
            "min": data_min_date.date() if data_min_date else None,
            "max": data_max_date.date() if data_max_date else None,
        }
        self.setup_plots()

    def setup_plots(self):
        """
        Sets up the plots for this widget.

        Adds three plots to the PlotCollection:
        1. top_tracks: a bar chart of the top 10 tracks by hours played, with a hovertemplate that shows the track name and artist.
        2. top_artists: a bar chart of the top 10 artists by hours played.
        3. top_podcasts: a bar chart of the top 10 podcasts by hours played.
        """
        self.plots = PlotCollection(
            layout={
                "plot_bgcolor": "#E5ECF6",
                "xaxis": {
                    "fixedrange": True,
                    "gridcolor": "white",
                    "title": {"text": "Hours Played"},
                },
                "yaxis": {"fixedrange": True, "showticklabels": False},
            },
            config={
                "responsive": True,
                "displayModeBar": False,
            },
        )
        self.plots.add_plot_from_trace(
            name="top_tracks",
            trace=(
                self.get_top_chart_trace,
                {
                    "feature": DataLabels.TRACK_NAME.value,
                    "media_type": "track",
                    "limit": 10,
                    "hovertemplate": r"<b>%{text}</b> - %{customdata[1]}<br><extra>Played for %{customdata[0]}</extra>",
                    "additional_features": [DataLabels.ARTIST.value],
                },
            ),
            parent=self,
        )
        self.plots.add_plot_from_trace(
            name="top_artists",
            trace=(
                self.get_top_chart_trace,
                {
                    "feature": DataLabels.ARTIST.value,
                    "media_type": "track",
                    "limit": 10,
                    "hovertemplate": None,
                    "additional_features": [],
                },
            ),
            parent=self,
        )
        self.plots.add_plot_from_trace(
            name="top_podcasts",
            trace=(
                self.get_top_chart_trace,
                {
                    "feature": DataLabels.PODCAST_NAME.value,
                    "media_type": "episode",
                    "limit": 10,
                    "hovertemplate": None,
                    "additional_features": [],
                },
            ),
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
        Resets the date range widgets and updates all plots.
        """
        self.reset_date_range_widget()

    @staticmethod
    def _get_chart_trace(x, y, text) -> dict:
        """
        Generates a horizontal bar chart trace.

        Parameters
        ----------
        x : list
            The list of names of the items (e.g. track names, artist names, etc.)
        y : list
            The list of values for each item (e.g. playtime, number of plays, etc.)
        text : list
            The list of text to display on the bars of the chart.

        Returns
        -------
        dict
            The trace dictionary.
        """
        return {
            "type": "bar",
            "name": "Top Tracks",
            "orientation": "h",
            "x": y,
            "y": x,
            "text": text,
            "textposition": "inside",
            "insidetextanchor": "start",
        }

    def on_date_range_change_forward(
        self, value: Dict[str, int] | None
    ) -> Dict[str, datetime.date]:
        """
        Called when the date_range_widget is changed.
        Sets the value of self.date_range, which requires a dict of the form {"min": datetime.date, "max": datetime.date}.
        """

        if value is None:
            return {"min": datetime.date.today(), "max": datetime.date.today()}
        range_min_days, range_max_days = value["min"], value["max"]
        data_min_date, _ = self.data_manager.get_min_max_date()
        if data_min_date is None:
            return {"min": datetime.date.today(), "max": datetime.date.today()}
        min_date = data_min_date.date() + datetime.timedelta(days=range_min_days)
        max_date = data_min_date.date() + datetime.timedelta(days=range_max_days)

        self.plots.update_plots()

        return {"min": min_date, "max": max_date}

    def on_date_range_change_backward(
        self, value: Dict[str, datetime.date] | None
    ) -> Dict[str, int]:
        """
        Called when the date_range attribute of this widget is changed.
        Sets the value of the date_range_widget, which requires a dict of the form {"min": number, "max": number}.
        """

        if value is None:
            return {"min": 0, "max": 1}

        self_min_date, self_max_date = value["min"], value["max"]

        data_min_date, _ = self.data_manager.get_min_max_date()
        if data_min_date is None:
            return {"min": 0, "max": 1}
        min_date = (self_min_date - data_min_date.date()).days
        max_date = (self_max_date - data_min_date.date()).days

        self.plots.update_plots()

        return {"min": min_date, "max": max_date}

    def reset_date_range_widget(self):
        """
        Resets the date range widget.
        Gets the earliest and latest dates from the data manager, and sets the date range to the range between the two.
        If the data is empty, does nothing.
        """

        data_start_date, data_end_date = self.data_manager.get_min_max_date()

        if data_start_date is None or data_end_date is None:
            return

        self.date_range = {"min": data_start_date.date(), "max": data_end_date.date()}
        days = (data_end_date - data_start_date).days
        self.date_range_widget.max = days

    def time_span_controls(self):
        """
        Initializes and configures the date range controls for the widget.

        This method sets up a range widget for selecting a time span, binding its
        visibility and value to the streaming data availability and current date range.
        It also sets up a label to display the selected date range.

        The range widget's visibility is controlled by the presence of streaming data
        and its value is synchronized with the date_range attribute, allowing for both
        forward and backward transformations.

        The method also ensures that the date range widget is reset to the correct
        initial state by calling reset_date_range_widget.
        """

        # the range widget
        self.date_range_widget = (
            ui.range(min=0, max=1, value={"min": 0, "max": 1})
            .bind_visibility_from(
                self.data_manager, "streaming_data", lambda sd: not sd.is_empty()
            )
            .classes("w-dvw")
        ).bind_value(
            self,
            "date_range",
            forward=self.on_date_range_change_forward,
            backward=self.on_date_range_change_backward,
        )
        # reset the widget
        self.reset_date_range_widget()

        # the label that displays the selected date range
        ui.label("").bind_text_from(
            target_object=self,
            target_name="date_range",
            backward=lambda v: f"From {v['min'] if v else ''} to {v['max'] if v else ''}.",
        ).bind_visibility_from(
            self.data_manager, "streaming_data", lambda sd: not sd.is_empty()
        ).classes("w-screen")

    def get_top(self, features: str, media_type: str, limit: int = 10) -> pl.DataFrame:
        """
        Get the top items with the most playtime for the given features and media_type.

        Parameters
        ----------
        features : str
            The column name(s) in the data to group by.
        media_type : str
            The type of media to filter by.
            Valid values are found in DataManager.read_audio_streaming_file
        limit : int, optional
            The number of results to return. Defaults to 10.

        Returns
        -------
        pl.DataFrame
            The top items with the most playtime.
        """
        return (
            self.data_manager.streaming_data.filter(
                pl.col(DataLabels.TIMESTAMP.value).is_between(
                    self.date_range["min"], self.date_range["max"]
                )
            )
            .filter(pl.col(DataLabels.MEDIA_TYPE.value) == media_type)
            .group_by(features)
            .agg(pl.sum(DataLabels.MILLISECONDS_PLAYED.value))
            .sort(DataLabels.MILLISECONDS_PLAYED.value, descending=True)
            .limit(limit)
            .sort(DataLabels.MILLISECONDS_PLAYED.value, descending=False)
            .with_columns(
                pl.duration(
                    milliseconds=pl.col(DataLabels.MILLISECONDS_PLAYED.value)
                ).alias("duration")
            )
        )

    def get_top_chart_trace(
        self, feature, media_type, hovertemplate=None, additional_features=[], limit=10
    ) -> Dict:
        """
        Generates a chart trace for the top features by playtime.

        Parameters
        ----------
        feature : str
            The primary feature to group by for the chart (e.g., track name, artist name).
        media_type : str
            The type of media to filter the data by (e.g., track, episode).
        hovertemplate : str, optional
            The template string for the hover labels. Defaults to a template showing the feature name and playtime.
        additional_features : list, optional
            Additional features to include in the custom data for hover labels.
        limit : int, optional
            The number of top features to include in the trace. Defaults to 10.

        Returns
        -------
        Dict
            A dictionary representing the chart trace.
        """

        if self.data_manager.streaming_data.is_empty():
            return None
        most_listened_features = self.get_top(
            features=[feature] + additional_features, media_type=media_type, limit=limit
        )

        feature_names = most_listened_features[feature].to_list()

        durations = most_listened_features["duration"]
        hours_played = (durations.dt.total_seconds() / 3600).to_list()

        trace = self._get_chart_trace(
            x=feature_names, y=hours_played, text=feature_names
        )
        hovertemplate = (
            hovertemplate or r"%{text}<br><extra>Played for %{customdata[0]}</extra>"
        )
        trace.update(
            hovertemplate=hovertemplate,
            customdata=[
                (humanize.precisedelta(d, suppress=["days"], format="%0.0f"), *f)
                for d, *f in zip(
                    durations,
                    *[most_listened_features[f].to_list() for f in additional_features],
                )
            ],
        )

        return trace

    def get_total_music_play_time(self):
        if self.data_manager.streaming_data.is_empty():
            return 0
        return (
            self.data_manager.streaming_data.filter(
                pl.col(DataLabels.MEDIA_TYPE.value) == "track"
            )
            .with_columns(
                pl.duration(
                    milliseconds=pl.col(DataLabels.MILLISECONDS_PLAYED.value)
                ).alias("duration")
            )
            .select(pl.col("duration"))
            .to_series()
            .drop_nulls()
            .sum()
        )

    def total_music_play_time_label_text(self):
        return f"The time you spent listening to music is {humanize.naturaldelta(self.get_total_music_play_time())}."

    def get_unique_tracks(self):
        if self.data_manager.streaming_data.is_empty():
            return 0
        return (
            self.data_manager.streaming_data.filter(
                pl.col(DataLabels.MEDIA_TYPE.value) == "track"
            )
            .select(pl.col(DataLabels.TRACK_NAME.value))
            .to_series()
            .drop_nulls()
            .unique()
            .len()
        )

    def unique_tracks_label_text(self):
        return f"You listened to {self.get_unique_tracks()} unique tracks."

    def get_unique_artists(self):
        if self.data_manager.streaming_data.is_empty():
            return 0
        return (
            self.data_manager.streaming_data.filter(
                pl.col(DataLabels.MEDIA_TYPE.value) == "track"
            )
            .select(pl.col(DataLabels.ARTIST.value))
            .to_series()
            .drop_nulls()
            .unique()
            .len()
        )

    def unique_artists_label_text(self):
        return f"You listened to {self.get_unique_artists()} unique artists."

    def create_music_analysis_section(self):
        ui.markdown("## Music Analysis")
        # Total music play time label
        ui.label("").bind_text_from(
            self.data_manager,
            "streaming_data",
            backward=lambda sd: self.total_music_play_time_label_text(),
        )
        with ui.grid(rows=1, columns=r"50% 50%").classes("w-dvw"):
            with ui.column():  # Top tracks plot and unique tracks label
                self.plots.create_plot("top_tracks")

                # Unique tracks label
                ui.label("").bind_text_from(
                    self.data_manager,
                    "streaming_data",
                    backward=lambda sd: self.unique_tracks_label_text(),
                )
            with ui.column():  # Top artists plot and unique artists label
                self.plots.create_plot("top_artists")

                # Unique artists label
                ui.label("").bind_text_from(
                    self.data_manager,
                    "data_manager",
                    backward=lambda sd: self.unique_artists_label_text(),
                )

    def get_total_podcast_play_time(self):
        if self.data_manager.streaming_data.is_empty():
            return 0
        return (
            self.data_manager.streaming_data.filter(
                pl.col(DataLabels.MEDIA_TYPE.value) == "episode"
            )
            .with_columns(
                pl.duration(
                    milliseconds=pl.col(DataLabels.MILLISECONDS_PLAYED.value)
                ).alias("duration")
            )
            .select(pl.col("duration"))
            .to_series()
            .drop_nulls()
            .sum()
        )

    def total_podcast_time_label_text(self):
        return f"The time you spent listening to podcasts is {humanize.naturaldelta(self.get_total_podcast_play_time())}."

    def get_unique_podcasts(self):
        if self.data_manager.streaming_data.is_empty():
            return 0
        return (
            self.data_manager.streaming_data.filter(
                pl.col(DataLabels.MEDIA_TYPE.value) == "episode"
            )
            .select(pl.col(DataLabels.PODCAST_NAME.value))
            .to_series()
            .drop_nulls()
            .unique()
            .len()
        )

    def unique_podcasts_label_text(self):
        return f"You listened to {self.get_unique_podcasts()} unique podcasts."

    def create_podcast_analysis_section(self):
        ui.markdown("## Podcast Analysis")

        # Total podcast play time label
        ui.label("").bind_text_from(
            self.data_manager,
            "streaming_data",
            backward=lambda sd: self.total_podcast_time_label_text(),
        )
        with ui.grid(rows=1, columns=r"50% 50%").classes("w-dvw"):
            with ui.column():
                self.plots.create_plot("top_podcasts")

                # Unique podcasts label
                ui.label("").bind_text_from(
                    self.data_manager,
                    "streaming_data",
                    backward=lambda sd: self.unique_podcasts_label_text(),
                )

    def create_widget(self, *args, **kwargs) -> element.Element:
        ui.label("No data loaded").bind_visibility_from(
            self.data_manager, "streaming_data", lambda sd: sd.is_empty()
        )
        with ui.column().bind_visibility_from(
            self.data_manager, "streaming_data", lambda sd: not sd.is_empty()
        ) as widget:
            self.time_span_controls()
            self.create_music_analysis_section()
            self.create_podcast_analysis_section()

        return widget
