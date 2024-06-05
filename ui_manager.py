from abc import ABC, abstractmethod
from enum import Enum

from multiprocessing import Manager, Queue
from nicegui import ui, element, run
import polars as pl

from data_manager import DataManager

class Page(ABC):
    data_manager: DataManager
    
    def __init__(self, data_manager: DataManager) -> None:
        self.data_manager = data_manager
        
    @abstractmethod
    def __call__(self, *args: element.Any, **kwds: element.Any) -> None:
        pass
    
class MainPage(Page):
    def handle_multi_upload(self, event) -> None:
        self.data_manager.append_files(event)
        
    @staticmethod
    def data_loaded_label_text(data_manager: DataManager) -> str:
        return f"Data from {len(data_manager.files_loaded)} files loaded."\
            if not data_manager.streaming_data.is_empty() else "No data loaded."
    
    @staticmethod
    def audio_features_loaded_label_text(data_manager: DataManager) -> str:
        if data_manager.audio_features.is_empty():
            return "No audio features loaded."
        unique_track_ids = data_manager.get_unique_track_ids()
        intersection = set(data_manager.audio_features['id']).intersection(unique_track_ids)
        return f"Loaded audio features cover {round(100 * len(intersection) / len(unique_track_ids), 2)}% of tracks in the data set."
        
    async def get_audio_features_callback(self, queue, progressbar, dialog, client_id, client_secret):
        progressbar.visible = True
        audio_features = await run.cpu_bound(
            self.data_manager.get_audio_features_from_spotify,
            queue, spotify_client_id=client_id, spotify_client_secret=client_secret
            )
        self.data_manager.audio_features = audio_features
        ui.notify("Audio Features loaded.")
        progressbar.visible = False
        dialog.close()
        
    def __call__(self, *args: element.Any, **kwds: element.Any) -> None:
        # streaming history info label
        with ui.label() as label:
            label.bind_text_from(self, 'data_manager', lambda dm: self.data_loaded_label_text(dm))
            with ui.tooltip() as tooltip:
                tooltip.style('white-space: pre-wrap')
                tooltip.bind_text_from(self, 'data_manager', lambda dm: '\n'.join(sorted(dm.files_loaded)))
                tooltip.bind_visibility_from(self, 'data_manager', lambda dm: not dm.streaming_data.is_empty())
        with ui.row():
            ui.label().bind_text_from(self, 'data_manager', lambda dm: self.audio_features_loaded_label_text(dm)) # audio features info label
            ui.button("Download Audio Features", on_click=lambda: ui.download(self.data_manager.audio_features_as_bytes(), "audio_features.json", "application/json")).bind_enabled_from(self, 'data_manager', lambda dm: not dm.audio_features.is_empty())
        
        # streaming history upload
        ui.upload(multiple=True, max_files=20, max_file_size=20_000_000,
                on_rejected=lambda e: ui.notification("upload failed"),
                on_multi_upload=lambda event: self.handle_multi_upload(event))
        
        # audio features upload facility
        with ui.row():
            ui.label("Get Audio Features")
            
            # spotify api client info dialog
            with ui.dialog() as dialog, ui.card():
                queue = Manager().Queue()
                ui.timer(0.1, callback=lambda: progressbar.set_value(queue.get() if not queue.empty() else progressbar.value))
                client_id = ui.input(label="Spotify API Client ID", placeholder="Your Client ID")
                client_secret = ui.input(label="Spotify API Client Secret", placeholder="Your Client Secret")
                with ui.row():
                    ui.button("Get Track Audio Features", on_click=lambda: self.get_audio_features_callback(queue, progressbar, dialog, client_id.value, client_secret.value))
                    ui.button("Cancel", on_click=dialog.close)
                progressbar = ui.circular_progress(value=0, max=100).props('instant-feedback')
                progressbar.visible = False
            # audio features from file upload
            ui.button("From Spotify", on_click=dialog.open).bind_enabled_from(self.data_manager, 'streaming_data', lambda x: not x.is_empty())
            
            ui.upload(label="From File", on_upload=lambda e: self.data_manager.get_audio_features_from_file(e))
        ui.button("Go to Table Page", on_click=lambda: ui.navigate.to("/table")).bind_enabled_from(self.data_manager, 'streaming_data', lambda x: not x.is_empty())

class TablePage(Page):
    data_table: element.Element
    def __init__(self, data_manager: DataManager) -> None:
        super().__init__(data_manager)
        self.data_table = None
    
    def create_data_table(self, dataframe: pl.DataFrame) -> ui.table:
        columns = [
            {'name': column, 'label': column.capitalize(), 'field': column, 'sortable': True}
            for column in dataframe.columns
        ]
        rows = dataframe.to_dicts()
        return ui.table(columns=columns, rows=rows, pagination=100)
    
    def on_submit(self):
        if self.data_table is not None:
            self.data_table.delete()
        self.data_table = self.create_data_table(self.data_manager.get_data())
        
    def __call__(self, *args: element.Any, **kwds: element.Any) -> None:
        with ui.row():
            ui.select(self.data_manager.streaming_data.columns, label="Group by", multiple=True, clearable=True, on_change=self.data_manager.group_by_aggregate_parser.process_group_by_change_event)
            ui.select(self.data_manager.group_by_aggregate_parser.aggregate_choices, clearable=True, label="Aggregate function", on_change=self.data_manager.group_by_aggregate_parser.process_aggregate_function_change_event)
            ui.select(self.data_manager.streaming_data.columns, label="Aggregate by", clearable=True, on_change=self.data_manager.group_by_aggregate_parser.process_aggregate_by_change_event)
            min_date, max_date = self.data_manager.get_min_max_date()
            ui.date(value=min_date, on_change=self.data_manager.group_by_aggregate_parser.process_start_date_change_event)
            ui.date(value=max_date, on_change=self.data_manager.group_by_aggregate_parser.process_end_date_change_event)
            
        ui.button("Submit", on_click=self.on_submit)
        

class Pages(Enum):
    MAIN = 1
    TABLE = 2

class UIManager:
    data_manager: DataManager
    
    pages = {
        Pages.MAIN: MainPage,
        Pages.TABLE: TablePage,
    }
    
    def __init__(self, data_manager: DataManager) -> None:
        self.data_manager = data_manager
    
    def create_page(self, page: Pages) -> None:
        self.pages[page](data_manager=self.data_manager)()
    