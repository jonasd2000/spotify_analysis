from abc import ABC, abstractmethod

from data_manager import DataManager


class Page(ABC):
    data_manager: DataManager
    
    def __init__(self, data_manager: DataManager) -> None:
        self.data_manager = data_manager
        
    @abstractmethod
    def create_page(self, *args, **kwargs) -> None:
        pass
    