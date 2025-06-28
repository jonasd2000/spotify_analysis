from abc import ABC, abstractmethod
from typing import List

from nicegui import element

from data_manager import DataManager
from .events import EventType


class Widget(ABC):
    """
    Base class for all widgets.

    Attributes:
        parent (Widget): The parent widget.
    """

    _parent: "Widget"
    children: List["Widget"]

    def __init__(self, parent: "Widget" = None) -> None:
        self._parent = None
        self.children = []
        
        self.set_parent(parent)

    def __del__(self):
        if self._parent:
            self._parent.remove_child(self)

    def print_tree(self, indent=0):
        """
        Recursively prints the widget tree.

        :param indent: The number of spaces to indent the output.
        """
        print(" " * indent + str(self))
        for child in self.children:
            child.print_tree(indent + 2)

    @property
    def parent(self) -> "Widget":
        return self._parent

    def set_parent(self, parent: "Widget") -> None:
        """
        Sets the parent of the widget.

        If the widget already has a parent, it is removed from the current parent's
        children before setting the new parent. Once the new parent is set, the widget
        is added to the new parent's children.

        Parameters
        ----------
        parent : Widget
            The new parent widget.
        """

        if self.parent:
            self.parent.remove_child(self)
        self._parent = parent
        if self.parent:
            self.parent.add_child(self)

    def add_child(self, child: "Widget") -> None:
        self.children.append(child)

    def remove_child(self, child: "Widget") -> None:
        self.children.remove(child)

    def emit_event(self, event_type: EventType, *args, propagate_upwards: bool=True, sender: "Widget" = None, **kwargs):
        """
        Emits an event to this widget and its event receivers.

        Parameters
        ----------
        event_type : EventType
            The type of the event to emit.
        *args
            Arguments to pass to the event handlers.
        propagate_upwards : bool, optional
            Whether to propagate the event upwards to the parent widget. Default is True.
        sender : Widget, optional
            The widget that sent the event. If not provided, the event is assumed to have been sent by this widget.
        **kwargs
            Additional keyword arguments to pass to the event handlers.

        """
        sender = sender or self
        
        # if the event was sent by this widget, call the on_event method
        if sender is self:
            self.on_event(sender=self, event_type=event_type, *args, **kwargs)
        
        # do not propagate the event upwards if this widget has no parent
        propagate_upwards &= (self.parent is not None)
        
        # get the event receivers
        event_receivers = self.children + ([self.parent] if propagate_upwards else [])
        
        for widget in event_receivers:
            # skip the widget that sent the event
            if widget is sender:
                continue
            widget._on_event(sender=self, event_type=event_type, *args, **kwargs)

    def on_event(self, event_type: EventType, *args, **kwargs) -> None:
        """
        Handle an event.

        This method is called by the framework to handle events.
        Override this method to handle events.

        Args:
            event_type (EventType): The type of the event.
            *args: Additional arguments for the event.
            **kwargs: Additional keyword arguments for the event.
        """
        pass
    
    def _on_event(self, sender: "Widget", event_type: EventType, *args, **kwargs):
        self.on_event(sender=sender, event_type=event_type, *args, **kwargs)
        if sender is self:
            return
        self.emit_event(event_type=event_type, *args, sender=sender, **kwargs)

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


class DataWidget(Widget):
    """
    Base class for widgets that use data from a data manager.
    
    Attributes:
        data_manager (DataManager): The data manager.
    """
    
    data_manager: DataManager
    
    def __init__(self, data_manager, parent = None):
        super().__init__(parent)
        self.data_manager = data_manager

