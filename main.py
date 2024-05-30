from data_manager import DataManager
from ui_manager import UIManager
from nicegui import ui

data_manager = DataManager()
ui_manager = UIManager(data_manager)
    
@ui.page("/")
def main_page() -> None:
    date_label = ui.label(f"No data loaded.")
    ui.upload(multiple=True, max_files=20, max_file_size=20_000_000,
              on_rejected=lambda e: ui.notification("upload failed"),
              on_multi_upload=lambda e: ui_manager.handle_multi_upload(e, date_label))
    
@ui.page("/table")
def table_page() -> None:
    ui_manager.create_table_page()

ui.run()
