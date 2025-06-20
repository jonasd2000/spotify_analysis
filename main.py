from data_manager import DataManager
from ui.ui import UI, Pages
from nicegui import ui

data_manager = DataManager()
ui_manager = UI(data_manager)
    
@ui.page("/")
def main_page() -> None:
    ui_manager.load_page(Pages.MAIN)
    
@ui.page("/analysis")
def analysis_page() -> None:
    ui.button("Back", on_click=lambda: ui.navigate.to("/"))
    ui_manager.load_page(Pages.ANALYSIS)
    
@ui.page("/table")
def table_page() -> None:
    ui.button("Back", on_click=lambda: ui.navigate.to("/"))
    ui_manager.load_page(Pages.TABLE)

ui.run()
