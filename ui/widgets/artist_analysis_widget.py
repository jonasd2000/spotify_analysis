import polars as pl
from nicegui import ui

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
            self.data_manager.streaming_data["master_metadata_album_artist_name"]
            .drop_nulls()
            .unique()
            .to_list()
        )

    def on_artist_change(self, select_artist: str) -> str:
        """
        Called when the artist_select widget is changed.
        Sets the value of self.selected_artist.
        """
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
        min_date = self.data_manager.streaming_data["ts"].min()
        max_date = self.data_manager.streaming_data["ts"].max()
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
        data = (
            self.data_manager.streaming_data.filter(
                pl.col("master_metadata_album_artist_name") == selected_artist
            )
            .group_by(
                pl.col("ts").dt.year().alias("year"),
                pl.col("ts").dt.month().alias("month"),
            )
            .agg(pl.sum("ms_played"))
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
            "y": (data["ms_played"] / 3600000).to_list(),
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
        return widget
