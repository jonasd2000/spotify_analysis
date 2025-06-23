from nicegui import ui

from .widgets.data_widget import DataWidget
from .widgets.overview_widget import OverviewWidget
from .widgets.query_widget import QueryWidget
from .widgets.widget import Widget


class AnalysisHome(Widget):
    def __init__(self, data_manager):
        super().__init__(data_manager)
        self.overview_widget = OverviewWidget(
            parent=self, data_manager=self.data_manager
        )
        self.query_widget = QueryWidget(parent=self, data_manager=self.data_manager)
        self.data_widget = DataWidget(parent=self, data_manager=self.data_manager)

    def on_event(self, name, *args, propagate=True, **kwargs):
        match name:
            case "data_change":
                self.overview_widget.on_event(
                    name=name, propagate=False, *args, **kwargs
                )
                self.query_widget.on_event(name=name, propagate=False, *args, **kwargs)
            case _:
                pass

        return super().on_event(name, propagate=propagate, *args, **kwargs)

    def create_widget(self, *args, **kwargs):
        with ui.expansion(text="Files", icon="folder").classes("w-dvw"):
            self.data_widget.create_widget()
        with ui.tabs() as tabs:
            overview = ui.tab(name="overview", label="Overview")
            artist_analysis = ui.tab(name="artist_analysis", label="Artist Analysis")
            custom_query = ui.tab(name="custom_query", label="Custom Query")
        with ui.tab_panels(tabs, value="overview"):
            with ui.tab_panel(overview):
                self.overview_widget.create_widget()
            with ui.tab_panel(artist_analysis):
                ui.label("Artist Analysis")
            with ui.tab_panel(custom_query):
                self.query_widget.create_widget()
