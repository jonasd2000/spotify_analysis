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
        
        with ui.dialog() as dialog, ui.card():
            client_id = ui.input(label="Spotify API Client ID", placeholder="Your Client ID")
            client_secret = ui.input(label="Spotify API Client Secret", placeholder="Your Client Secret")
            with ui.row():
                def get_audio_features_callback(data_manager, dialog):
                    data_manager.get_track_audio_features_from_spotify(spotify_client_id=client_id.value, spotify_client_secret=client_secret.value)
                    dialog.close()
                ui.button("Get Track Audio Features", on_click=lambda: get_audio_features_callback(data_manager, dialog))
                ui.button("Cancel", on_click=dialog.close)
        ui.button("From Spotify", on_click=dialog.open).bind_enabled_from(data_manager, 'streaming_data', lambda x: not x.is_empty())
        
        ui.upload(label="From File", on_upload=lambda e: data_manager.get_track_audio_features_from_file(e))
    ui.button("Go to Table Page", on_click=lambda: ui.navigate.to("/table"))
    
@ui.page("/table")
def table_page() -> None:
    ui.button("Back", on_click=lambda: ui.navigate.to("/"))
    ui_manager.create_table_page()

ui.run()
