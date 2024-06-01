from nicegui import ui, element
import polars as pl

from data_manager import DataManager

class UIManager:
    data_manager: DataManager
    
    data_table: element.Element
    
    def __init__(self, data_manager: DataManager) -> None:
        self.data_manager = data_manager
        self.data_table = None
    
    def create_main_page(self) -> None:
        date_label = ui.label(f"No data loaded.")
        audio_features_available = ui.label().bind_text_from(self.data_manager, 'audio_features', lambda x: f"Audio Features {"not " if x.is_empty() else ""}available.")
        ui.upload(multiple=True, max_files=20, max_file_size=20_000_000,
                on_rejected=lambda e: ui.notification("upload failed"),
                on_multi_upload=lambda e: self.ui_manager.handle_multi_upload(e, date_label))
        with ui.row():
            ui.label("Get Track Audio Features")
            
            with ui.dialog() as dialog, ui.card():
                client_id = ui.input(label="Spotify API Client ID", placeholder="Your Client ID")
                client_secret = ui.input(label="Spotify API Client Secret", placeholder="Your Client Secret")
                with ui.row():
                    def get_audio_features_callback(data_manager, dialog):
                        data_manager.get_track_audio_features_from_spotify(spotify_client_id=client_id.value, spotify_client_secret=client_secret.value)
                        dialog.close()
                    ui.button("Get Track Audio Features", on_click=lambda: get_audio_features_callback(self.data_manager, dialog))
                    ui.button("Cancel", on_click=dialog.close)
            ui.button("From Spotify", on_click=dialog.open).bind_enabled_from(self.data_manager, 'streaming_data', lambda x: not x.is_empty())
            
            ui.upload(label="From File", on_upload=lambda e: self.data_manager.get_audio_features_from_file(e))
        ui.button("Go to Table Page", on_click=lambda: ui.navigate.to("/table")).bind_enabled_from(self.data_manager, 'streaming_data', lambda x: not x.is_empty())
    
    def handle_multi_upload(self, event, date_label) -> None:
        files_succesfully_loaded = self.data_manager.append_files(event)
        if files_succesfully_loaded > 0:
            min_date, max_date = self.data_manager.get_min_max_date()
            date_label.text = f"data loaded from {min_date.date()} to {max_date.date()}"
    
    def create_data_table(self, dataframe: pl.DataFrame) -> None:
        columns = [
            {'name': column, 'label': column.capitalize(), 'field': column, 'sortable': True}
            for column in dataframe.columns
        ]
        rows = dataframe.to_dicts()
        return ui.table(columns=columns, rows=rows, pagination=100)
    
    def create_table_page(self) -> None:
        with ui.row():
            ui.select(self.data_manager.streaming_data.columns, label="Group by", multiple=True, clearable=True, on_change=self.data_manager.group_by_aggregate_parser.process_group_by_change_event)
            ui.select(self.data_manager.group_by_aggregate_parser.aggregate_choices, clearable=True, label="Aggregate function", on_change=self.data_manager.group_by_aggregate_parser.process_aggregate_function_change_event)
            ui.select(self.data_manager.streaming_data.columns, label="Aggregate by", clearable=True, on_change=self.data_manager.group_by_aggregate_parser.process_aggregate_by_change_event)
            min_date, max_date = self.data_manager.get_min_max_date()
            ui.date(value=min_date, on_change=self.data_manager.group_by_aggregate_parser.process_start_date_change_event)
            ui.date(value=max_date, on_change=self.data_manager.group_by_aggregate_parser.process_end_date_change_event)
            
        def on_submit():
            if self.data_table is not None:
                self.data_table.delete()
            self.data_table = self.create_data_table(self.data_manager.get_data())
        
        ui.button("Submit", on_click=on_submit)
        
