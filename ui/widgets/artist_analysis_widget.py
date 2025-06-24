from itertools import zip_longest

import humanize
import polars as pl
from nicegui import ui

from data_labels import DataLabels

from .widget import Widget


class ArtistAnalysisWidget(Widget):
    top_graph_layouts = {
        "plot_bgcolor": "#E5ECF6",
        "xaxis": {"fixedrange": True},
        "yaxis": {
            "fixedrange": True,
            "gridcolor": "white",
            "title": {"text": "Hours Played"},
        },
    }
    top_graph_config = {
        "responsive": True,
        "displayModeBar": False,
    }

    charts = {}
    artist_top_five_labels = [None] * 5

    def on_event(self, name, *args, propagate=True, **kwargs):
        match name:
            case "data_change":
                self.on_data_change()
            case _:
                pass
        return super().on_event(name, *args, propagate=propagate, **kwargs)

    def on_data_change(self):
        self.artist_select.set_options(self.get_artist_names())
        self.update_charts()

    def get_artist_names(self):
        if self.data_manager.streaming_data.is_empty():
            return []
        return (
            self.data_manager.streaming_data[DataLabels.ARTIST.value]
            .drop_nulls()
            .unique()
            .to_list()
        )

    def on_artist_change(self, select_artist: str) -> str:
        """
        Called when the artist_select widget is changed.
        Sets the value of self.selected_artist.
        """
        self.create_artist_top_five()
        self.update_charts()
        return select_artist

    def update_charts(self):
        new_trace = self.create_artist_over_time_trace()
        if "artist_over_time" not in self.charts:
            return
        self.charts["artist_over_time"]["fig"]["data"][0] = new_trace
        self.charts["artist_over_time"]["plot"].update()

    def create_artist_over_time_trace(self):
        if self.data_manager.streaming_data.is_empty():
            return None

        # time dataframe
        # a dataframe which contains all year month combinations from the date range of the streaming data
        min_date = self.data_manager.streaming_data[DataLabels.TIMESTAMP.value].min()
        max_date = self.data_manager.streaming_data[DataLabels.TIMESTAMP.value].max()
        time_df = (
            pl.DataFrame(
                {
                    "date": pl.date_range(
                        start=min_date,
                        end=max_date,
                        interval="1mo",
                        closed="both",
                        eager=True,
                    ),
                }
            )
            .with_columns(
                pl.col("date").dt.year().alias("year"),
                pl.col("date").dt.month().alias("month"),
            )
            .drop("date")
        )

        selected_artist = self.artist_select.value
        if selected_artist is None:
            return {}

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

    def create_artist_over_time_plot(self):
        trace = self.create_artist_over_time_trace()
        fig = {
            "data": [
                trace,
            ],
            "layout": self.top_graph_layouts,
            "config": self.top_graph_config,
        }

        artist_over_time_chart = ui.plotly(fig)

        self.charts["artist_over_time"] = {
            "fig": fig,
            "plot": artist_over_time_chart,
        }

        return artist_over_time_chart

    def create_artist_top_five(self):
        if self.data_manager.streaming_data.is_empty():
            for i in range(5):
                self.artist_top_five_labels[i] = ui.label("")
            return

        selected_artist = self.artist_select.value
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
            .with_columns(
                pl.duration(
                    milliseconds=pl.col(DataLabels.MILLISECONDS_PLAYED.value)
                ).alias("duration")
            )
            .limit(5)
        )

        for indexed_row, label in zip_longest(
            enumerate(data.iter_rows(named=True)), self.artist_top_five_labels
        ):
            if indexed_row is None:
                label.set_text("")
                continue
            i, row = indexed_row
            text = f"{i + 1}. {row[DataLabels.TRACK_NAME.value]} ({humanize.precisedelta(row['duration'], format='%0.0f')})"
            label.set_text(text)

    def create_widget(self, *args, **kwargs):
        with ui.column() as widget:
            self.artist_select = ui.select(
                self.get_artist_names(),
                label="Artist",
                with_input=True,
                on_change=self.on_artist_change,
            )
            with ui.grid(rows=1, columns=r"100%").classes("w-dvw"):
                self.create_artist_over_time_plot()
                self.create_artist_top_five()
        return widget
