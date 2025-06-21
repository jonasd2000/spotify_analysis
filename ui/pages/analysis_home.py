from nicegui import ui
import polars as pl
import humanize

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
            'y': x,
            'text': text,
            'textposition': 'inside',
            'insidetextanchor': 'start',
            'hovertemplate': '<b>%{y}</b><br>%{x} hours played<extra></extra>',
        }
    
    def get_top(self, feature, media_type, limit=10):
        return self.data_manager.streaming_data\
            .filter(pl.col('media_type') == media_type)\
            .group_by(feature)\
            .agg(pl.sum('ms_played'))\
            .sort('ms_played', descending=True).limit(limit)\
            .sort('ms_played', descending=False).with_columns(pl.duration(milliseconds=pl.col('ms_played')).alias('duration'))
    
    def create_track_analysis_chart(self):
        most_listened_tracks = self.get_top(('master_metadata_track_name', 'master_metadata_album_artist_name'), 'track')
        
        track_names = most_listened_tracks['master_metadata_track_name'].to_list()
        artist_names = most_listened_tracks['master_metadata_album_artist_name'].to_list()
        
        durations = most_listened_tracks['duration']
        hours_played = (durations.dt.total_seconds() / 3600).to_list()
        
        trace = self._get_chart_data(x=track_names, y=hours_played, text=track_names)
        trace.update(
            customdata=[(an, humanize.precisedelta(d, format="%0.0f")) for an, d in zip(artist_names, durations)],
            hovertemplate=r"%<b>{text}</b> - %{customdata[0]}<br><extra>Played for %{customdata[1]}</extra>",
        )
        
        fig = {
            'data': [
                trace,
            ],
            'layout': self.top_graph_layouts,
            'config': self.top_graph_config,
        }
        
        ui.plotly(fig)
            
    def create_artist_analysis_chart(self):
        most_listened_artists = self.get_top('master_metadata_album_artist_name', 'track')
            
        artist_names = most_listened_artists['master_metadata_album_artist_name'].to_list()
        
        durations = most_listened_artists['duration']
        hours_played = (durations.dt.total_seconds() / 3600).to_list()
        
        trace = self._get_chart_data(x=artist_names, y=hours_played, text=artist_names)
        trace.update(
            customdata=[humanize.precisedelta(d, format="%0.0f") for d in durations],
            hovertemplate=r"%{text}<br><extra>Played for %{customdata}</extra>",
        )
        
        fig = {
            'data': [
                trace,
            ],
            'layout': self.top_graph_layouts,
            'config': self.top_graph_config,
        }
        
        ui.plotly(fig)
    
    def create_podcast_analysis_chart(self):
        most_listened_podcasts = self.get_top('episode_show_name', 'episode')
        
        podcast_names = most_listened_podcasts['episode_show_name'].to_list()
        
        durations = most_listened_podcasts['duration']
        hours_played = (durations.dt.total_seconds() / 3600).to_list()
        
        trace = self._get_chart_data(x=podcast_names, y=hours_played, text=podcast_names)
        trace.update(
            customdata=[humanize.precisedelta(d, format="%0.0f") for d in durations],
            hovertemplate=r"%{text}<br><extra>Played for %{customdata}</extra>",
        )
        
        fig = {
            'data': [
                trace,
            ],
            'layout': self.top_graph_layouts,
            'config': self.top_graph_config,
        }
        
        return ui.plotly(fig)
    
    def create_track_analysis_section(self):
        unique_tracks = self.data_manager.streaming_data.select(pl.col('master_metadata_track_name')).to_series().drop_nulls().unique().len()
        total_time = self.data_manager.streaming_data.filter(pl.col('media_type') == 'track')\
            .with_columns(pl.duration(milliseconds=pl.col('ms_played')).alias('duration')).select(pl.col('duration')).to_series().drop_nulls().sum()
        with ui.row():
            self.create_track_analysis_chart()
            with ui.column():
                ui.label(f"You listened to a total of {unique_tracks} unique tracks.")
                ui.label(f"The time you spent listening to tracks is {humanize.naturaldelta(total_time)}.")
            
    def create_artist_analysis_section(self):
        unique_artists = self.data_manager.streaming_data.select(pl.col('master_metadata_album_artist_name')).to_series().drop_nulls().unique().len()
        with ui.row():
            self.create_artist_analysis_chart()
            with ui.column():
                ui.label(f"You listened to a total of {unique_artists} unique artists.")
            
    def create_podcast_analysis_section(self):
        unique_podcasts = self.data_manager.streaming_data.select(pl.col('episode_show_name')).to_series().drop_nulls().unique().len()
        total_time = self.data_manager.streaming_data.filter(pl.col('media_type') == 'episode')\
            .with_columns(pl.duration(milliseconds=pl.col('ms_played')).alias('duration')).select(pl.col('duration')).to_series().drop_nulls().sum()
        with ui.row():
            self.create_podcast_analysis_chart()
            with ui.column():
                ui.label(f"You listened to a total of {unique_podcasts} unique podcasts.")
                ui.label(f"The time you spent listening to podcasts is {humanize.naturaldelta(total_time)}.")
    
    def create_page(self, *args, **kwargs) -> None:
        with ui.column():
            self.create_track_analysis_section()
            self.create_artist_analysis_section()
            self.create_podcast_analysis_section()