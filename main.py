from app import App
from nicegui import ui

app = App()
    
@ui.page("/")
def main_page() -> None:
    app.ui_manager.create_main_page()

ui.run()
