from nicegui import ui

from data_manager import DataManager

class UIManager:
    data_manager: DataManager
    
    def __init__(self, data_manager: DataManager) -> None:
        self.data_manager = data_manager
    
    def create_ui(self) -> None:
        ui.label(str(self.data_manager.path))
        ui.button('BUTTON', on_click=lambda: ui.notify('button was pressed'))
    
    def run(self) -> None:
        self.create_ui()
        ui.run()
