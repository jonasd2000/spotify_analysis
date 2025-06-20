from enum import Enum

from data_manager import DataManager

from .pages import MainPage, TablePage

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
    
    def load_page(self, page: Pages) -> None:
        page = self.pages[page](data_manager=self.data_manager)
        page.create_page()
    