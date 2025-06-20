from typing import Set
from bidict import bidict

from nicegui import ui, element
import polars as pl

from .page import Page
from data_manager import DataManager

class TablePage(Page):
    _group_by_columns: Set[str]
    _aggregate_columns: Set[str]
    
    column_display_names = bidict({ # fix column names
            "master_metadata_track_name": "Track Title",
            "master_metadata_album_artist_name": "Artist",
            "master_metadata_album_album_name": "Album",
            "conn_country": "Country",
            "incognito_mode": "Incognito Mode",
            "ip_addr_decrypted": "IP Address",
            "ms_played": "Time spent listening to track (ms)",
            "minutes_played": "Time spent listening to track (min)",
            "hours_played": "Time spent listening to track (h)",
            "offline": "Offline",
            "spotify_track_uri": "Spotify URI",
            "user_agent_decrypted": "User Agent",
            "ts": "Timestamp",
        })
    
    data_table: element.Element
    
    def __init__(self, data_manager: DataManager) -> None:
        super().__init__(data_manager)
        self.data_table = None
        self._group_by_columns = self.filter_group_by_columns(self.data_manager.streaming_data)
        self._aggregate_columns = self.filter_aggregate_columns(self.data_manager.streaming_data)
    
    def filter_group_by_columns(self, streaming_data: pl.DataFrame) -> Set[str]:
        return set(streaming_data.columns).intersection({
            "master_metadata_track_name",
            "master_metadata_album_artist_name",
            "master_metadata_album_album_name",
            "conn_country", "ip_addr_decrypted", "platform",
            "incognito_mode", "offline",
            "year", "month", "weekday",
            "reason_start", "reason_end",
            "shuffle", "skipped",
            "spotify_track_uri",
            "username",
        })
    def filter_aggregate_columns(self, streaming_data: pl.DataFrame) -> Set[str]:
        return set(streaming_data.columns).intersection({
            "ts", "ms_played",
        })
    def get_group_by_columns(self) -> Set[str]:
        return sorted([self.column_display_names.get(column, column) for column in self._group_by_columns])
    def get_aggregate_columns(self) -> Set[str]:
        return sorted([self.column_display_names.get(column, column) for column in self._aggregate_columns])
    
    
    def with_additional_columns(self, dataframe: pl.DataFrame) -> pl.DataFrame:
        if "ms_played" in dataframe.columns:
            dataframe = dataframe.with_columns(
                (pl.col("ms_played")/60000).round(2).alias("minutes_played"),
                (pl.col("ms_played")/3600000).round(2).alias("hours_played"),
            )
        if "master_metadata_track_name" in dataframe.columns:
            dataframe = dataframe.with_columns(
                pl.col("master_metadata_track_name").alias("Track Details"), # TODO: need a function that converts a track name to a link
            )
        return dataframe
    
    def create_data_table(self, dataframe: pl.DataFrame) -> ui.table:
        dataframe = self.with_additional_columns(dataframe)
        columns = [
            {'name': column, 'label': self.column_display_names.get(column, column.capitalize()), 'field': column, 'sortable': True}
            for column in dataframe.columns
        ]
        rows = dataframe.to_dicts()
        return ui.table(columns=columns, rows=rows, pagination=100)
    
    def on_group_by_change(self, event):
        self.data_manager.group_by_aggregate_parser.set_group_by([self.column_display_names.inverse.get(v, v) for v in event.value])
    def on_aggregate_change(self, event):
        self.data_manager.group_by_aggregate_parser.set_aggregate_by(self.column_display_names.inverse.get(event.value, event.value))
    
    def on_submit(self):
        if self.data_table is not None:
            self.data_table.delete()
        self.data_table = self.create_data_table(self.data_manager.get_data())
        
    def create_page(self, *args: element.Any, **kwds: element.Any) -> None:
        with ui.row():
            ui.select(self.get_group_by_columns(), label="Group by", multiple=True, clearable=True, on_change=self.on_group_by_change)
            ui.select(self.data_manager.group_by_aggregate_parser.aggregate_choices, clearable=True, label="Aggregate function", on_change=self.data_manager.group_by_aggregate_parser.process_aggregate_function_change_event)
            ui.select(self.get_aggregate_columns(), label="Aggregate by", clearable=True, on_change=self.on_aggregate_change)
            min_date, max_date = self.data_manager.get_min_max_date()
            ui.date(value=min_date, on_change=self.data_manager.group_by_aggregate_parser.process_start_date_change_event)
            ui.date(value=max_date, on_change=self.data_manager.group_by_aggregate_parser.process_end_date_change_event)
            
        ui.button("Submit", on_click=self.on_submit)
        