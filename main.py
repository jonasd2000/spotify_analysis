from data_manager import DataManager
from ui_manager import UIManager
from nicegui import ui

data_manager = DataManager()
ui_manager = UIManager(data_manager)
    
@ui.page("/")
def main_page() -> None:
    ui_manager.create_main_page()
    
@ui.page("/table")
def table_page() -> None:
    ui.button("Back", on_click=lambda: ui.navigate.to("/"))
    ui_manager.create_table_page()

ui.run()
