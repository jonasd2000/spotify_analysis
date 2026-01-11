import logging
from nicegui import ui

from .widgets.track_analysis_widget import TrackAnalysisWidget
from .widgets.artist_analysis_widget import ArtistAnalysisWidget
from .widgets.data_loader_widget import DataLoaderWidget
from .widgets.overview_widget import OverviewWidget
from .widgets.metrics_widget import MetricsWidget
# from .widgets.query_widget import QueryWidget
from .widgets.widget import DataWidget

from .widgets.events import EventType

logger = logging.getLogger(__name__)


class AnalysisHome(DataWidget):
    def __init__(self, data_manager, parent=None):
        super().__init__(data_manager, parent)
        self.data_loader_widget = DataLoaderWidget(parent=self, data_manager=self.data_manager)
        self.overview_widget = OverviewWidget(parent=self, data_manager=self.data_manager)
        self.track_analysis_widget = TrackAnalysisWidget(parent=self, data_manager=self.data_manager)
        self.artist_analysis_widget = ArtistAnalysisWidget(parent=self, data_manager=self.data_manager)
        self.metrics_widget = MetricsWidget(parent=self, data_manager=self.data_manager)
        # self.query_widget = QueryWidget(parent=self, data_manager=self.data_manager)

    async def create_widget(self, *args, **kwargs):
        logger.debug("Creating AnalysisHome widget...")
        
        logger.debug("Setting up data manager...")
        await self.data_manager.setup()
        
        with ui.expansion(text="Files", icon="folder").classes("w-dvw"):
            await self.data_loader_widget.create_widget()
            
        with ui.tabs() as tabs:
            overview = ui.tab(name="overview", label="Overview")
            track_analysis = ui.tab(name="track_analysis", label="Track Analysis")
            artist_analysis = ui.tab(name="artist_analysis", label="Artist Analysis")
            metrics = ui.tab(name="metrics", label="Metrics")
        #     # custom_query = ui.tab(name="custom_query", label="Custom Query")
        with ui.tab_panels(tabs, value="overview"):
            with ui.tab_panel(overview):
                await self.overview_widget.create_widget()
            with ui.tab_panel(track_analysis):
                await self.track_analysis_widget.create_widget()
            with ui.tab_panel(artist_analysis):
                await self.artist_analysis_widget.create_widget()
            with ui.tab_panel(metrics):
                await self.metrics_widget.create_widget()
        #     # with ui.tab_panel(custom_query):
        #     #     self.query_widget.create_widget()
        self.tabs = tabs

    async def on_event(self, event_type, *args, **kwargs):
        await super().on_event(event_type, *args, **kwargs)
        match event_type:
            case EventType.ANALYSE_TRACK_REQUEST:
                logger.debug("ANALYSE_TRACK_REQUEST event received")
                if not "track_id" in kwargs:
                    error = TypeError("track_id kwarg required for ANALYSE_TRACK_REQUEST event")
                    logger.exception(error)
                    raise error
                track_id = kwargs["track_id"]
                self.analyse_track(track_id=track_id)
            case _:
                pass

    def analyse_track(self, track_id: int):
        logger.debug(f"Switching to Analyse Track: {track_id}")
        self.tabs.set_value("track_analysis")
        self.track_analysis_widget.track_select.set_value(track_id)