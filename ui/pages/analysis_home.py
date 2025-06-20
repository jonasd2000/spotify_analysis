from nicegui import ui
import polars as pl

from .page import Page


class AnalysisHome(Page):
    def create_track_analysis_section(self):
        most_listened_tracks = self.data_manager.streaming_data\
            .group_by('master_metadata_track_name')\
            .agg(pl.sum('ms_played'))\
            .sort('ms_played', descending=True).limit(10)
            
        rows = most_listened_tracks.to_dicts()
        ui.table(rows=rows)
    
    def create_artist_analysis_section(self):
        most_listened_artists = self.data_manager.streaming_data\
            .group_by('master_metadata_album_artist_name')\
            .agg(pl.sum('ms_played'))\
            .sort('ms_played', descending=True).limit(10)
            
        rows = most_listened_artists.to_dicts()
        ui.table(rows=rows)
    
    def create_page(self, *args, **kwargs) -> None:
        with ui.row():
            self.create_track_analysis_section()
            self.create_artist_analysis_section()