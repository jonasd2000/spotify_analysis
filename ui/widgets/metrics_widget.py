import datetime

from nicegui import ui
import polars as pl

from data_labels import DataLabels

from .widget import DataWidget
from .plots import Plot


class MetricsWidget(DataWidget):
    def __init__(self, data_manager, parent=None):
        super().__init__(data_manager, parent)

        self.diversity_plot = Plot(
            trace=(self.create_diversity_trace, {}),
            layout={
                "plot_bgcolor": "#E5ECF6",
                "xaxis": {"fixedrange": True},
                "yaxis": {
                    "fixedrange": True,
                    "gridcolor": "white",
                    "title": {"text": "Diversity Score"},
                },
            },
            config={
                "responsive": True,
                "displayModeBar": False,
            },
            parent=self
        )

    def create_diversity_trace(self, *args, **kwargs):
        if self.data_manager.streaming_data.is_empty():
            return None
        # time dataframe
        # a dataframe which contains all year month combinations from the date range of the streaming data
        min_date = self.data_manager.streaming_data[DataLabels.TIMESTAMP.value].min(
        )
        max_date = self.data_manager.streaming_data[DataLabels.TIMESTAMP.value].max(
        )
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

        data = self.data_manager.streaming_data.group_by(
            pl.col(DataLabels.TIMESTAMP.value).dt.year().alias("year"),
            pl.col(DataLabels.TIMESTAMP.value).dt.month().alias("month"),
            pl.col(DataLabels.ARTIST.value),
        ).agg(
            pl.sum(DataLabels.MILLISECONDS_PLAYED.value)
        )

        diversity_table = []
        top_n = 5
        for year, month in time_df.iter_rows():
            ym_data = data.filter((pl.col("year") == year)
                                  & (pl.col("month") == month))
            total_time = ym_data.sum()[DataLabels.MILLISECONDS_PLAYED.value][0]
            top_n_time = ym_data.sort(DataLabels.MILLISECONDS_PLAYED.value, descending=True).head(
                    top_n
                ).sum()[DataLabels.MILLISECONDS_PLAYED.value][0]
            top_n_share = ((total_time-top_n_time) / top_n_time) if total_time > 0 else 0
            diversity_table.append(
                {"date": datetime.date(year, month, 1), "diversity": top_n_share}
            )

        diversity_table = pl.DataFrame(diversity_table)

        return {
            "x": diversity_table["date"].to_list(),
            "y": diversity_table["diversity"].to_list(),
            "type": "line", 
            "name": "diversity"
        }

    def create_widget(self, *args, **kwargs):
        with ui.column() as widget:
            with ui.grid(rows=1, columns=r"100%").classes("w-dvw"):
                self.diversity_plot.create_widget()
        return widget
