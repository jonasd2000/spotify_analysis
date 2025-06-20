from nicegui import ui
import polars as pl

from .page import Page


class AnalysisHome(Page):
    def create_track_analysis_section(self):
        most_listened_tracks = self.data_manager.streaming_data\
            .filter(pl.col('media_type') == 'track')\
            .group_by('master_metadata_track_name')\
            .agg(pl.sum('ms_played'))\
            .sort('ms_played', descending=True).limit(10)
            
        track_names = most_listened_tracks['master_metadata_track_name'].to_list()
        # artist_names = most_listened_tracks['master_metadata_album_artist_name'].to_list()
        
        # display_text = [f"{artist_names[i]} - {track_names[i]}" for i in range(len(track_names))]
        
        ms_played = most_listened_tracks['ms_played'].to_list()
        
        ui.echart({
            'xAxis': {'type': 'category', 'data': track_names},
            'yAxis': {'type': 'value'},
            'series': [{'type': 'bar', 'data': ms_played}],
            'tooltip': {'formatter': "{b}"},
        })
    
    def create_artist_analysis_section(self):
        most_listened_artists = self.data_manager.streaming_data\
            .filter(pl.col('media_type') == 'track')\
            .group_by('master_metadata_album_artist_name')\
            .agg(pl.sum('ms_played'))\
            .sort('ms_played', descending=True).limit(10)
            
        artist_names = most_listened_artists['master_metadata_album_artist_name'].to_list()
        ms_played = most_listened_artists['ms_played'].to_list()
        
        ui.echart({
            'xAxis': {'type': 'category', 'data': artist_names},
            'yAxis': {'type': 'value'},
            'series': [{'type': 'bar', 'data': ms_played}],
            'tooltip': {'formatter': "{b}"},
        })
    
    def create_podcast_analysis_section(self):
        most_listened_podcasts = self.data_manager.streaming_data\
            .filter(pl.col('media_type') == 'episode')\
            .group_by('episode_show_name')\
            .agg(pl.sum('ms_played'))\
            .sort('ms_played', descending=True).limit(10)
            
        podcast_names = most_listened_podcasts['episode_show_name'].to_list()
        ms_played = most_listened_podcasts['ms_played'].to_list()
        
        ui.echart({
            'xAxis': {'type': 'category', 'data': podcast_names},
            'yAxis': {'type': 'value'},
            'series': [{'type': 'bar', 'data': ms_played}],
            'tooltip': {'formatter': "{b}"},
        })
    
    def create_page(self, *args, **kwargs) -> None:
        with ui.row():
            self.create_track_analysis_section()
            self.create_artist_analysis_section()
            self.create_podcast_analysis_section()