from nicegui import ui
import polars as pl

from .page import Page


class AnalysisHome(Page):
    top_graph_layouts = {
        'plot_bgcolor': '#E5ECF6',
        'xaxis': {'fixedrange': True, 'gridcolor': 'white'},
        'yaxis': {'fixedrange': True, 'showticklabels': False},
    }
    top_graph_config = {
        'responsive': True,
        'displayModeBar': False,
    }
    
    @staticmethod
    def _get_chart_data(x, y, text) -> dict:
        return {
            'type': 'bar',
            'name': 'Top Tracks',
            'orientation': 'h',
            'x': y,
            'y': text,
            'text': x,
            'textposition': 'inside',
            'insidetextanchor': 'start',
            'hovertemplate': '<b>%{y}</b><br>%{x} ms played<extra></extra>',
        }
    
    def create_track_analysis_section(self):
        most_listened_tracks = self.data_manager.streaming_data\
            .filter(pl.col('media_type') == 'track')\
            .group_by('master_metadata_track_name', 'master_metadata_album_artist_name')\
            .agg(pl.sum('ms_played'))\
            .sort('ms_played', descending=True).limit(10).sort('ms_played', descending=False)
            
        track_names = most_listened_tracks['master_metadata_track_name'].to_list()
        artist_names = most_listened_tracks['master_metadata_album_artist_name'].to_list()
        display_text = [f"{track_name} - {artist_name}" for track_name, artist_name in zip(track_names, artist_names)]
        
        ms_played = most_listened_tracks['ms_played'].to_list()
        fig = {
            'data': [
                self._get_chart_data(x=track_names, y=ms_played, text=display_text),
            ],
            'layout': self.top_graph_layouts,
            'config': self.top_graph_config,
        }
        ui.plotly(fig)
            
    def create_artist_analysis_section(self):
        most_listened_artists = self.data_manager.streaming_data\
            .filter(pl.col('media_type') == 'track')\
            .group_by('master_metadata_album_artist_name')\
            .agg(pl.sum('ms_played'))\
            .sort('ms_played', descending=True).limit(10).sort('ms_played', descending=False)
            
        artist_names = most_listened_artists['master_metadata_album_artist_name'].to_list()
        ms_played = most_listened_artists['ms_played'].to_list()
        
        fig = {
            'data': [
                self._get_chart_data(x=artist_names, y=ms_played, text=artist_names),
            ],
            'layout': self.top_graph_layouts,
            'config': self.top_graph_config,
        }
        
        ui.plotly(fig)
    
    def create_podcast_analysis_section(self):
        most_listened_podcasts = self.data_manager.streaming_data\
            .filter(pl.col('media_type') == 'episode')\
            .group_by('episode_show_name')\
            .agg(pl.sum('ms_played'))\
            .sort('ms_played', descending=True).limit(10).sort('ms_played', descending=False)
            
        podcast_names = most_listened_podcasts['episode_show_name'].to_list()
        ms_played = most_listened_podcasts['ms_played'].to_list()
        
        fig = {
            'data': [
                self._get_chart_data(x=podcast_names, y=ms_played, text=podcast_names),
            ],
            'layout': self.top_graph_layouts,
            'config': self.top_graph_config,
        }
        
        ui.plotly(fig)
    
    def create_page(self, *args, **kwargs) -> None:
        with ui.row():
            self.create_track_analysis_section()
            self.create_artist_analysis_section()
            self.create_podcast_analysis_section()