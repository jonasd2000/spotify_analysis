from typing import Tuple, Dict
import datetime

from nicegui import ui
import polars as pl
import humanize

from .page import Page


class AnalysisHome(Page):
    top_graph_layouts = {
        'plot_bgcolor': '#E5ECF6',
        'xaxis': {'fixedrange': True, 'gridcolor': 'white', 'title': {'text': 'Hours Played'}},
        'yaxis': {'fixedrange': True, 'showticklabels': False},
    }
    top_graph_config = {
        'responsive': True,
        'displayModeBar': False,
    }
    
    charts: Dict
    date_range: Tuple[datetime.date, datetime.date]
    
    def __init__(self, data_manager):
        super().__init__(data_manager)
        self.date_range = self.data_manager.get_min_max_date()
        self.charts = {}
    
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
        }
    
    def get_top(self, feature, media_type, limit=10):
        return self.data_manager.streaming_data\
            .filter(pl.col('ts').is_between(self.date_range[0], self.date_range[1]))\
            .filter(pl.col('media_type') == media_type)\
            .group_by(feature)\
            .agg(pl.sum('ms_played'))\
            .sort('ms_played', descending=True).limit(limit)\
            .sort('ms_played', descending=False).with_columns(pl.duration(milliseconds=pl.col('ms_played')).alias('duration'))
    
    def on_date_range_change(self, value):
        mini, maxi = value['min'], value['max']
        curr_min_date, _ = self.data_manager.get_min_max_date()
        min_date = curr_min_date.date() + datetime.timedelta(days=mini)
        max_date = curr_min_date.date() + datetime.timedelta(days=maxi)
        
        self.date_range = min_date, max_date
        
        self.update_charts()
        
        return f"From {min_date} to {max_date}"
    
    def time_span_controls(self):
        start_date, end_date = self.data_manager.get_min_max_date()
        days = (end_date - start_date).days
        
        date_range = ui.range(min=0, max=days, value={'min': 0, 'max': days})
        ui.label(f"From {start_date} to {end_date}").bind_text_from(
            target_object=date_range,
            target_name='value',
            backward=self.on_date_range_change
        )
    
    def get_top_chart_trace(self, feature, media_type, hovertemplate=None, additional_features=[], limit=10) -> Dict:
        most_listened_features = self.get_top(feature=[feature] + additional_features, media_type=media_type, limit=limit)
    
        feature_names = most_listened_features[feature].to_list()
        
        durations = most_listened_features['duration']
        hours_played = (durations.dt.total_seconds() / 3600).to_list()
        
        trace = self._get_chart_data(x=feature_names, y=hours_played, text=feature_names)
        hovertemplate = hovertemplate or r"%{text}<br><extra>Played for %{customdata[0]}</extra>"
        trace.update(
            hovertemplate=hovertemplate,
            customdata=[(humanize.precisedelta(d, suppress=['days'], format="%0.0f"), *f) for d, *f in zip(durations, *[most_listened_features[f].to_list() for f in additional_features])],
        )
        
        return trace
        
    def create_feature_top_chart(self, name, feature, media_type, hovertemplate=None, additional_features=[], limit=10):
        trace = self.get_top_chart_trace(feature=feature, media_type=media_type, hovertemplate=hovertemplate, additional_features=additional_features, limit=limit)
        
        fig = {
            'data': [
                trace,
            ],
            'layout': self.top_graph_layouts,
            'config': self.top_graph_config,
        }
        
        self.charts[name] = {
            'feature': feature,
            'media_type': media_type,
            'hovertemplate': hovertemplate,
            'additional_features': additional_features,
            'limit': limit,
            'fig': fig
        }
        
        plot = ui.plotly(fig)
        self.charts[name]['plot'] = plot
        
        return plot
    
    def update_charts(self):
        for chart_name, chart_data in self.charts.items():
            new_trace = self.get_top_chart_trace(
                feature=chart_data["feature"],
                media_type=chart_data["media_type"],
                hovertemplate=chart_data["hovertemplate"],
                additional_features=chart_data["additional_features"],
                limit=chart_data["limit"],
            )
            
            self.charts[chart_name]["fig"]["data"][0] = new_trace
            
            plot = chart_data["plot"]
            plot.update()
    
    def create_music_analysis_section(self):
        total_music_time = self.data_manager.streaming_data.filter(pl.col('media_type') == 'track')\
            .with_columns(pl.duration(milliseconds=pl.col('ms_played')).alias('duration')).select(pl.col('duration')).to_series().drop_nulls().sum()
        unique_tracks = self.data_manager.streaming_data.select(pl.col('master_metadata_track_name')).to_series().drop_nulls().unique().len()
        unique_artists = self.data_manager.streaming_data.select(pl.col('master_metadata_album_artist_name')).to_series().drop_nulls().unique().len()
        
        ui.markdown('## Music Analysis')
        ui.label(f"The time you spent listening to music is {humanize.naturaldelta(total_music_time)}.")
        with ui.grid(rows=1, columns=r'50% 50%').classes('w-dvw'):
            with ui.column():
                self.create_feature_top_chart(
                    name='top_tracks',
                    feature='master_metadata_track_name',
                    media_type='track', limit=10,
                    hovertemplate=r"<b>%{text}</b> - %{customdata[1]}<br><extra>Played for %{customdata[0]}</extra>",
                    additional_features=['master_metadata_album_artist_name']
                )
                
                ui.label(f"You listened to a total of {unique_tracks} unique tracks.")
            with ui.column():
                self.create_feature_top_chart(name='top_artists', feature='master_metadata_album_artist_name', media_type='track', limit=10)  
                
                ui.label(f"You listened to a total of {unique_artists} unique artists.")  
            
    def create_podcast_analysis_section(self):
        total_podcast_time = self.data_manager.streaming_data.filter(pl.col('media_type') == 'episode')\
            .with_columns(pl.duration(milliseconds=pl.col('ms_played')).alias('duration')).select(pl.col('duration')).to_series().drop_nulls().sum()
        unique_podcasts = self.data_manager.streaming_data.select(pl.col('episode_show_name')).to_series().drop_nulls().unique().len()
        
        ui.markdown('## Podcast Analysis')
        ui.label(f"The time you spent listening to podcasts is {humanize.naturaldelta(total_podcast_time)}.")
        with ui.grid(rows=1, columns=r'50% 50%').classes('w-dvw'):
            with ui.column():
                self.create_feature_top_chart(name='top_podcasts',feature='episode_show_name', media_type='episode', limit=10)
                
                ui.label(f"You listened to a total of {unique_podcasts} unique podcasts.")
    
    def create_page(self, *args, **kwargs) -> None:
        with ui.column():
            self.time_span_controls()
            self.create_music_analysis_section()
            self.create_podcast_analysis_section()