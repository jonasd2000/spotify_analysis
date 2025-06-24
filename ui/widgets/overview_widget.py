import datetime
from typing import Dict, List

import humanize
import polars as pl
from nicegui import element, ui

from .widget import Widget


class OverviewWidget(Widget):
    top_graph_layouts = {
        "plot_bgcolor": "#E5ECF6",
        "xaxis": {
            "fixedrange": True,
            "gridcolor": "white",
            "title": {"text": "Hours Played"},
        },
        "yaxis": {"fixedrange": True, "showticklabels": False},
    }
    top_graph_config = {
        "responsive": True,
        "displayModeBar": False,
    }

    charts: Dict
    date_range: Dict[str, datetime.date]

    def __init__(self, data_manager, parent=None):
        super().__init__(data_manager, parent)
        data_min_date, data_max_date = self.data_manager.get_min_max_date()
        self.date_range = {
            "min": data_min_date.date() if data_min_date else None,
            "max": data_max_date.date() if data_max_date else None,
        }
        self.charts = {}

    def on_event(self, name, *args, propagate=True, **kwargs):
        match name:
            case "data_change":
                self.on_data_change()
            case _:
                pass
        return super().on_event(name, propagate=propagate, *args, **kwargs)

    def on_data_change(self):
        self.reset_date_range_widget()
        self.update_charts()

    @staticmethod
    def _get_chart_data(x, y, text) -> dict:
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

        self.update_charts()

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

        self.update_charts()

        return {"min": min_date, "max": max_date}

    def reset_date_range_widget(self):
        data_start_date, data_end_date = self.data_manager.get_min_max_date()

        if data_start_date is None or data_end_date is None:
            return

        self.date_range = {"min": data_start_date.date(), "max": data_end_date.date()}
        days = (data_end_date - data_start_date).days
        self.date_range_widget.max = days

    def time_span_controls(self):
        self.date_range_widget = (
            ui.range(min=0, max=1, value={"min": 0, "max": 1})
            .bind_visibility_from(
                self.data_manager, "streaming_data", lambda sd: not sd.is_empty()
            )
            .classes("w-screen")
        ).bind_value(
            self,
            "date_range",
            forward=self.on_date_range_change_forward,
            backward=self.on_date_range_change_backward,
        )
        self.reset_date_range_widget()
        ui.label("").bind_text_from(
            target_object=self,
            target_name="date_range",
            backward=lambda v: f"From {v['min'] if v else ''} to {v['max'] if v else ''}.",
        ).bind_visibility_from(
            self.data_manager, "streaming_data", lambda sd: not sd.is_empty()
        ).classes("w-screen")

    def get_top(self, features: str, media_type: str, limit: int = 10) -> pl.DataFrame:
        return (
            self.data_manager.streaming_data.filter(
                pl.col("ts").is_between(self.date_range["min"], self.date_range["max"])
            )
            .filter(pl.col("media_type") == media_type)
            .group_by(features)
            .agg(pl.sum("ms_played"))
            .sort("ms_played", descending=True)
            .limit(limit)
            .sort("ms_played", descending=False)
            .with_columns(
                pl.duration(milliseconds=pl.col("ms_played")).alias("duration")
            )
        )

    def get_top_chart_trace(
        self, feature, media_type, hovertemplate=None, additional_features=[], limit=10
    ) -> Dict:
        if self.data_manager.streaming_data.is_empty():
            return None
        most_listened_features = self.get_top(
            features=[feature] + additional_features, media_type=media_type, limit=limit
        )

        feature_names = most_listened_features[feature].to_list()

        durations = most_listened_features["duration"]
        hours_played = (durations.dt.total_seconds() / 3600).to_list()

        trace = self._get_chart_data(
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

    def create_feature_top_chart(
        self,
        name: str,
        feature: str,
        media_type: str,
        hovertemplate: str = None,
        additional_features: List[str] = [],
        limit: int = 10,
    ):
        trace = self.get_top_chart_trace(
            feature=feature,
            media_type=media_type,
            hovertemplate=hovertemplate,
            additional_features=additional_features,
            limit=limit,
        )

        fig = {
            "data": [
                trace,
            ],
            "layout": self.top_graph_layouts,
            "config": self.top_graph_config,
        }

        plot = ui.plotly(fig)

        self.charts[name] = {
            "feature": feature,
            "media_type": media_type,
            "hovertemplate": hovertemplate,
            "additional_features": additional_features,
            "limit": limit,
            "fig": fig,
            "plot": plot,
        }

        return plot

    def update_charts(self):
        for chart_name, chart_data in self.charts.items():
            new_trace = self.get_top_chart_trace(
                feature=chart_data["feature"],
                media_type=chart_data["media_type"],
                hovertemplate=chart_data["hovertemplate"],
                additional_features=chart_data["additional_features"],
                limit=chart_data["limit"],
            )

            self.charts[chart_name]["fig"]["data"][0] = new_trace

            plot = chart_data["plot"]
            plot.update()

    def get_total_music_time(self):
        if self.data_manager.streaming_data.is_empty():
            return 0
        return (
            self.data_manager.streaming_data.filter(pl.col("media_type") == "track")
            .with_columns(
                pl.duration(milliseconds=pl.col("ms_played")).alias("duration")
            )
            .select(pl.col("duration"))
            .to_series()
            .drop_nulls()
            .sum()
        )

    def total_music_time_label_text(self):
        return f"The time you spent listening to music is {humanize.naturaldelta(self.get_total_music_time())}."

    def get_unique_tracks(self):
        if self.data_manager.streaming_data.is_empty():
            return 0
        return (
            self.data_manager.streaming_data.filter(pl.col("media_type") == "track")
            .select(pl.col("master_metadata_track_name"))
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
            self.data_manager.streaming_data.filter(pl.col("media_type") == "track")
            .select(pl.col("master_metadata_album_artist_name"))
            .to_series()
            .drop_nulls()
            .unique()
            .len()
        )

    def unique_artists_label_text(self):
        return f"You listened to {self.get_unique_artists()} unique artists."

    def create_music_analysis_section(self):
        ui.markdown("## Music Analysis")
        # Total music time label
        ui.label("").bind_text_from(
            self.data_manager,
            "streaming_data",
            backward=lambda sd: self.total_music_time_label_text(),
        )
        with ui.grid(rows=1, columns=r"50% 50%").classes("w-dvw"):
            with ui.column():
                self.create_feature_top_chart(
                    name="top_tracks",
                    feature="master_metadata_track_name",
                    media_type="track",
                    limit=10,
                    hovertemplate=r"<b>%{text}</b> - %{customdata[1]}<br><extra>Played for %{customdata[0]}</extra>",
                    additional_features=["master_metadata_album_artist_name"],
                )

                # Unique tracks label
                ui.label("").bind_text_from(
                    self.data_manager,
                    "streaming_data",
                    backward=lambda sd: self.unique_tracks_label_text(),
                )
            with ui.column():
                self.create_feature_top_chart(
                    name="top_artists",
                    feature="master_metadata_album_artist_name",
                    media_type="track",
                    limit=10,
                )

                # Unique artists label
                ui.label("").bind_text_from(
                    self.data_manager,
                    "data_manager",
                    backward=lambda sd: self.unique_artists_label_text(),
                )

    def get_total_podcast_time(self):
        if self.data_manager.streaming_data.is_empty():
            return 0
        return (
            self.data_manager.streaming_data.filter(pl.col("media_type") == "episode")
            .with_columns(
                pl.duration(milliseconds=pl.col("ms_played")).alias("duration")
            )
            .select(pl.col("duration"))
            .to_series()
            .drop_nulls()
            .sum()
        )

    def total_podcast_time_label_text(self):
        return f"The time you spent listening to podcasts is {humanize.naturaldelta(self.get_total_podcast_time())}."

    def get_unique_podcasts(self):
        if self.data_manager.streaming_data.is_empty():
            return 0
        return (
            self.data_manager.streaming_data.filter(pl.col("media_type") == "episode")
            .select(pl.col("episode_show_name"))
            .to_series()
            .drop_nulls()
            .unique()
            .len()
        )

    def unique_podcasts_label_text(self):
        return f"You listened to {self.get_unique_podcasts()} unique podcasts."

    def create_podcast_analysis_section(self):
        ui.markdown("## Podcast Analysis")
        ui.label("").bind_text_from(
            self.data_manager,
            "streaming_data",
            backward=lambda sd: self.total_podcast_time_label_text(),
        )
        with ui.grid(rows=1, columns=r"50% 50%").classes("w-dvw"):
            with ui.column():
                self.create_feature_top_chart(
                    name="top_podcasts",
                    feature="episode_show_name",
                    media_type="episode",
                    limit=10,
                )

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
