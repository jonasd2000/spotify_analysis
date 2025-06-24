from abc import ABC, abstractmethod

from nicegui import element

from data_manager import DataManager


class Widget(ABC):
    """
    Base class for all widgets.

    Attributes:
        parent (Widget): The parent widget.
        data_manager (DataManager): The data manager.
    """

    parent: "Widget"
    data_manager: DataManager

    def __init__(self, data_manager: DataManager, parent: "Widget" = None) -> None:
        self.data_manager = data_manager
        self.parent = parent

    def on_event(self, name, *args, propagate=True, **kwargs) -> None:
        """
        Handle an event.

        This method can be called when an event occurs in the widget.
        The event may be propagated to the parent widget.

        Args:
            name (str): The name of the event.
            *args: Additional arguments for the event.
            propagate (bool, optional): If True, propagate the event to the
                parent widget. Defaults to True.
            **kwargs: Additional keyword arguments for the event.
        """
        if propagate and self.parent:
            self.parent.on_event(name, *args, propagate=propagate, **kwargs)

    @abstractmethod
    def create_widget(self, *args, **kwargs) -> element.Element:
        """
        Create a widget.

        This method is called by the framework to create the widget. The
        method should return a NiceGUI Element that represents the widget.

        The method may receive additional arguments and keyword arguments, which
        are not specified here.

        Returns:
            Element: The NiceGUI Element for the widget.
        """
        pass
