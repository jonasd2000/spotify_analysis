from data_manager import DataManager
from ui_manager import UIManager
from nicegui import ui

data_manager = DataManager()
ui_manager = UIManager(data_manager)
    
@ui.page("/")
def main_page() -> None:
    date_label = ui.label(f"No data loaded.")
    audio_features_available = ui.label().bind_text_from(data_manager, 'audio_features', lambda x: f"Audio Features {"not " if x.is_empty() else ""}available.")
    ui.upload(multiple=True, max_files=20, max_file_size=20_000_000,
              on_rejected=lambda e: ui.notification("upload failed"),
              on_multi_upload=lambda e: ui_manager.handle_multi_upload(e, date_label))
    with ui.row():
        ui.label("Get Track Audio Features")
        ui.button("From Spotify", on_click=data_manager.load_track_data)
        ui.upload(label="From File", on_upload=lambda e: data_manager.load_track_data(e))
    ui.button("Go to Table Page", on_click=lambda: ui.go("/table"))
    
@ui.page("/table")
def table_page() -> None:
    ui_manager.create_table_page()

ui.run()
