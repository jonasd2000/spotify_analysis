import datetime
from typing import Set

import polars as pl
from bidict import bidict
from nicegui import element, ui

from data_labels import DataLabels
from data_manager import DataManager

from .widget import Widget


class GroupByAggregateParser:
    aggregate_choices = [
        "count",
        "sum",
        "min",
        "max",
        "mean",
    ]

    group_by: str
    aggregate_function: str
    aggregate_by: str

    start_date: datetime.date
    end_date: datetime.date

    def __init__(self) -> None:
        self.group_by = None
        self.aggregate_function = None
        self.aggregate_by = None

        self.start_date = None
        self.end_date = None

    def set_group_by(self, group_by: str) -> None:
        self.group_by = group_by

    def process_group_by_change_event(self, event) -> None:
        self.set_group_by(event.value)

    def get_group_by_expression(self) -> pl.Expr:
        if self.group_by is None:
            return None
        return pl.col(self.group_by)

    def set_aggregate_function(self, aggregate_function: str) -> None:
        self.aggregate_function = aggregate_function

    def process_aggregate_function_change_event(self, event) -> None:
        self.set_aggregate_function(event.value)

    def set_aggregate_by(self, aggregate_by: str) -> None:
        self.aggregate_by = aggregate_by

    def process_aggregate_by_change_event(self, event) -> None:
        self.set_aggregate_by(event.value)

    def get_aggregate_expression(self) -> pl.Expr:
        if self.aggregate_function is None:
            return None

        # aggregate functions that don't need a column
        match self.aggregate_function:
            case "count":
                return pl.count()
            case _:
                pass

        if self.aggregate_by is None:
            return None

        # aggregate functions that need a column to aggregate
        match self.aggregate_function:
            case "sum":
                return pl.col(self.aggregate_by).sum()
            case "min":
                return pl.col(self.aggregate_by).min()
            case "max":
                return pl.col(self.aggregate_by).max()
            case "mean":
                return pl.col(self.aggregate_by).mean()
            case _:
                return None

    def set_start_date(self, start_date: datetime.date) -> None:
        self.start_date = start_date

    def process_start_date_change_event(self, event) -> None:
        self.set_start_date(event.value)

    def set_end_date(self, end_date: datetime.date) -> None:
        self.end_date = end_date

    def process_end_date_change_event(self, event) -> None:
        self.set_end_date(event.value)

    def get_filter_expressions(self) -> list[pl.Expr]:
        filter_expressions = []

        if self.start_date is not None:
            filter_expressions.append(
                pl.col(DataLabels.TIMESTAMP.value)
                > pl.date(
                    self.start_date.year, self.start_date.month, self.start_date.day
                )
            )

        if self.end_date is not None:
            filter_expressions.append(
                pl.col(DataLabels.TIMESTAMP.value)
                < pl.date(self.end_date.year, self.end_date.month, self.end_date.day)
            )

        return filter_expressions


class QueryWidget(Widget):
    """
    Widget for handling data queries.
    """

    group_by_aggregate_parser = GroupByAggregateParser()

    _group_by_columns: Set[str]
    _aggregate_columns: Set[str]

    column_display_names = bidict(
        {  # fix column names
            DataLabels.TRACK_NAME.value: "Track Title",
            DataLabels.ARTIST.value: "Artist",
            DataLabels.ALBUM_NAME.value: "Album",
            DataLabels.COUNTRY.value: "Country",
            DataLabels.INCOGNITO_MODE.value: "Incognito Mode",
            "ip_addr_decrypted": "IP Address",
            DataLabels.MILLISECONDS_PLAYED.value: "Time spent listening to track (ms)",
            "minutes_played": "Time spent listening to track (min)",
            "hours_played": "Time spent listening to track (h)",
            DataLabels.OFFLINE.value: DataLabels.OFFLINE.value,
            DataLabels.TRACK_ID.value: "Spotify URI",
            "user_agent_decrypted": "User Agent",
            DataLabels.TIMESTAMP.value: "Timestamp",
        }
    )

    data_table: element.Element

    def __init__(self, data_manager: DataManager, parent: Widget = None) -> None:
        super().__init__(data_manager, parent)
        self.data_table = None
        self._group_by_columns = self.filter_group_by_columns(
            self.data_manager.streaming_data
        )
        self._aggregate_columns = self.filter_aggregate_columns(
            self.data_manager.streaming_data
        )

    def on_event(self, name, *args, propagate=True, **kwargs):
        match name:
            case "data_change":
                self.on_data_change()
            case _:
                pass
        return super().on_event(name, propagate=propagate, *args, **kwargs)

    def on_data_change(self):
        """
        Called when the 'data_change' event is received.
        Updates the group_by_columns, aggregate_columns, group_by_select, aggregate_select,
        min_date_widget, and max_date_widget to reflect the new data.
        """
        self._group_by_columns = self.filter_group_by_columns(
            self.data_manager.streaming_data
        )
        self._aggregate_columns = self.filter_aggregate_columns(
            self.data_manager.streaming_data
        )

        self.group_by_select.set_options(self.get_group_by_columns())
        self.aggregate_select.set_options(self.get_aggregate_columns())

        data_min_date, data_max_date = self.data_manager.get_min_max_date()
        self.min_date_widget.set_value(data_min_date.date())
        self.max_date_widget.set_value(data_max_date.date())

    def filter_group_by_columns(self, streaming_data: pl.DataFrame) -> Set[str]:
        return set(streaming_data.columns).intersection(
            {
                DataLabels.TRACK_NAME.value,
                DataLabels.ARTIST.value,
                DataLabels.ALBUM_NAME.value,
                DataLabels.COUNTRY.value,
                DataLabels.IP_ADDRESS.value,
                DataLabels.PLATFORM.value,
                DataLabels.INCOGNITO_MODE.value,
                DataLabels.OFFLINE.value,
                DataLabels.REASON_START.value,
                DataLabels.REASON_END.value,
                DataLabels.SHUFFLE.value,
                DataLabels.SKIPPED.value,
                DataLabels.TRACK_ID.value,
            }
        )

    def filter_aggregate_columns(self, streaming_data: pl.DataFrame) -> Set[str]:
        return set(streaming_data.columns).intersection(
            {
                DataLabels.TIMESTAMP.value,
                DataLabels.MILLISECONDS_PLAYED.value,
            }
        )

    def get_group_by_columns(self) -> Set[str]:
        return sorted(
            [
                self.column_display_names.get(column, column)
                for column in self._group_by_columns
            ]
        )

    def get_aggregate_columns(self) -> Set[str]:
        return sorted(
            [
                self.column_display_names.get(column, column)
                for column in self._aggregate_columns
            ]
        )

    def with_additional_columns(self, dataframe: pl.DataFrame) -> pl.DataFrame:
        """
        Adds additional columns to a dataframe, derived from existing columns.
        Adds 'minutes_played' and 'hours_played' columns if 'milliseconds_played' is present,
        and adds 'Track Details' column if 'track_name' is present.
        Returns the modified dataframe.
        """
        if DataLabels.MILLISECONDS_PLAYED.value in dataframe.columns:
            dataframe = dataframe.with_columns(
                (pl.col(DataLabels.MILLISECONDS_PLAYED.value) / 60000)
                .round(2)
                .alias("minutes_played"),
                (pl.col(DataLabels.MILLISECONDS_PLAYED.value) / 3600000)
                .round(2)
                .alias("hours_played"),
            )
        if DataLabels.TRACK_NAME.value in dataframe.columns:
            dataframe = dataframe.with_columns(
                pl.col(DataLabels.TRACK_NAME.value).alias(
                    "Track Details"
                ),  # TODO: need a function that converts a track name to a link
            )
        return dataframe

    def create_data_table(self, dataframe: pl.DataFrame) -> ui.table:
        """
        Creates a ui.table from a polars.DataFrame.

        The function takes a polars.DataFrame as an argument and
        adds additional columns.
        Then, it creates a ui.table with the columns and rows
        from the dataframe and returns the table.

        Args:
            dataframe (pl.DataFrame): The polars.DataFrame
                to be converted to a ui.table

        Returns:
            ui.table: A ui.table created from the dataframe
        """
        dataframe = self.with_additional_columns(dataframe)

        # create table columns
        columns = [
            {
                "name": column,
                "label": self.column_display_names.get(column, column.capitalize()),
                "field": column,
                "sortable": True,
            }
            for column in dataframe.columns
        ]
        rows = dataframe.to_dicts()
        return ui.table(columns=columns, rows=rows, pagination=100)

    def on_group_by_change(self, event):
        """
        Called when the group_by widget is changed.
        Sets the value of self.group_by_aggregate_parser.group_by
        to the selected columns.
        """
        self.group_by_aggregate_parser.set_group_by(
            [self.column_display_names.inverse.get(v, v) for v in event.value]
        )

    def on_aggregate_change(self, event):
        """
        Called when the aggregate widget is changed.
        Sets the value of self.group_by_aggregate_parser.aggregate_by
        to the selected aggregate column.
        """
        self.group_by_aggregate_parser.set_aggregate_by(
            self.column_display_names.inverse.get(event.value, event.value)
        )

    def get_data(self) -> pl.DataFrame:
        """
        Returns the filtered and grouped data according to the
        current selection of columns and aggregate function in the
        group_by and aggregate widgets.

        Returns:
            pl.DataFrame: The filtered and grouped data
        """
        data = self.data_manager.streaming_data
        for (
            filter_expression
        ) in self.group_by_aggregate_parser.get_filter_expressions():
            data = data.filter(filter_expression)
        data = data.group_by(
            self.group_by_aggregate_parser.get_group_by_expression()
        ).agg(self.group_by_aggregate_parser.get_aggregate_expression())

        return data

    def on_submit(self):
        """
        Called when the submit button is clicked.
        Deletes the current data table and creates a new one with the
        filtered and grouped data according to the current selection
        of columns and aggregate function in the group_by and
        aggregate widgets.
        """
        if self.data_table is not None:
            self.data_table.delete()

        self.data_table = self.create_data_table(self.get_data())

    def create_widget(self, *args, **kwds) -> element.Element:
        with ui.column() as widget:
            with ui.row():  # query options
                # create group_by and aggregate widgets
                self.group_by_select = ui.select(
                    self.get_group_by_columns(),
                    label="Group by",
                    multiple=True,
                    clearable=True,
                    on_change=self.on_group_by_change,
                )
                ui.select(
                    self.group_by_aggregate_parser.aggregate_choices,
                    clearable=True,
                    label="Aggregate function",
                    on_change=self.group_by_aggregate_parser.process_aggregate_function_change_event,
                )
                self.aggregate_select = ui.select(
                    self.get_aggregate_columns(),
                    label="Aggregate by",
                    clearable=True,
                    on_change=self.on_aggregate_change,
                )
                # create min_date and max_date widgets
                min_date, max_date = self.data_manager.get_min_max_date()
                self.min_date_widget = ui.date(
                    value=min_date,
                    on_change=self.group_by_aggregate_parser.process_start_date_change_event,
                )
                self.max_date_widget = ui.date(
                    value=max_date,
                    on_change=self.group_by_aggregate_parser.process_end_date_change_event,
                )

            ui.button("Submit", on_click=self.on_submit)

        return widget
