from abc import ABC, abstractmethod

from nicegui import element

from data_manager import DataManager


class Widget(ABC):
    parent: "Widget"
    data_manager: DataManager

    def __init__(self, data_manager: DataManager, parent: "Widget" = None) -> None:
        self.data_manager = data_manager
        self.parent = parent

    def on_event(self, name, *args, propagate=True, **kwargs) -> None:
        if propagate and self.parent:
            self.parent.on_event(name, *args, propagate=propagate, **kwargs)

    @abstractmethod
    def create_widget(self, *args, **kwargs) -> element.Element:
        pass
