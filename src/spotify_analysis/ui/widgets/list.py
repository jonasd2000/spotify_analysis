from itertools import zip_longest
from typing import List, Iterable, Callable, Tuple, Dict

from nicegui import ui

from .widget import Widget, UpdatableMixin

class LabelList(Widget, UpdatableMixin):
    labels: List[ui.label]
    text: Iterable[str] | Tuple[Callable, Dict]
    
    def __init__(self, length: int, text: Iterable[str] | Tuple[Callable, Dict], parent = None):
        super().__init__(parent)
        self.labels = [None for _ in range(length)]
        self.text = text
    
    def __len__(self):
        return len(self.labels)
    
    def get_text(self):
        if isinstance(self.text, tuple):
            return self.text[0](**self.text[1])
        else:
            return self.text
    
    @property
    def was_created(self):
        return all(label is not None for label in self.labels)
    
    def on_update(self):
        for i, (label, text_item) in enumerate(zip_longest(self.labels, self.get_text())):
            if text_item is None:
                self.labels[i].set_text("")
                continue
            self.labels[i].set_text(text_item)
    
    def create_widget(self, *args, **kwargs):
        text = self.get_text()
        with ui.column() as widget:
            for i, (label, text_item) in enumerate(zip_longest(self.labels, text)):
                self.labels[i] = ui.label(text=text_item)
                
        return widget
            