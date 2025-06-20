from nicegui import ui

from .page import Page


class AnalysisHome(Page):
    def create_track_analysis_section(self):
        pass
    
    def create_artist_analysis_section(self):
        pass
    
    def create_page(self, *args, **kwargs) -> None:
        with ui.row():
            self.create_track_analysis_section()
            self.create_artist_analysis_section()