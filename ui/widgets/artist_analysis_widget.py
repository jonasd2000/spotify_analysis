import datetime
from functools import partial

import humanize
import polars as pl
from nicegui import ui
from sqlalchemy import select, func as sql_func

from data.models import Artist, ListeningEvent, track_artist, Track

from .plots import Plot
from .widget import DataWidget
from .events import EventType


class ArtistOverTimePlot(Plot):
    async def on_event(self, event_type, *args, **kwargs):
        await super().on_event(event_type, *args, **kwargs)
        match event_type:
            case EventType.ARTIST_SELECTED:
                self.update()
            case _:
                pass

class ArtistAnalysisWidget(DataWidget):
    """
    Widget for artist analysis.
    """

    top_tracks_limit: int = 5
    top_tracks_info: list[tuple[int, str, int]]

    artist_over_time_plot: Plot

    def __init__(self, data_manager, parent=None):
        super().__init__(data_manager, parent)

        self.top_tracks_info = []

        # artist over time plot initialisation
        self.artist_over_time_plot = ArtistOverTimePlot(
            trace=(self.create_artist_over_time_trace, {}),
            layout={
                "plot_bgcolor": "#E5ECF6",
                "xaxis": {"fixedrange": True},
                "yaxis": {
                    "fixedrange": True,
                    "gridcolor": "white",
                    "title": {"text": "Hours Played"},
                },
            },
            config={
                "responsive": True,
                "displayModeBar": False,
            },
            parent=self,
        )

    async def get_artist_names(self) -> dict[int, str]:
        async with self.data_manager.async_session() as session:
            stmt = select(Artist.artist_id, Artist.artist_name).select_from(Artist).order_by(Artist.artist_name)
            result = await session.execute(stmt)
            artist_names = {
                row.artist_id: row.artist_name
                for row in result.all()
            }
            return artist_names

    async def on_event(self, event_type: EventType, *args, **kwargs):
        match event_type:
            case EventType.DATA_ADDED:
                await self.on_data_change()
            case EventType.ARTIST_SELECTED:
                await self.get_artist_top_tracks_info()
                self.update_artist_top_songs_list()
                await self.data_manager.get_artist_over_time_statistics(self.artist_select.value)
            case _:
                pass

    async def on_data_change(self):
        """
        Called when the 'data_change' event is received.
        """
        self.artist_select.set_options(await self.get_artist_names())

    async def on_artist_change(self, select_artist: int) -> None:
        """
        Called when the artist_select widget is changed.
        Sets the value of self.selected_artist.
        """
        await self.emit_event(EventType.ARTIST_SELECTED, propagate_upwards=False, artist=select_artist)

    def create_artist_over_time_trace(self):
        """
        Generates a chart trace for the hours played of the selected artist over time.

        Parameters
        ----------
        None

        Returns
        -------
        Dict
            A dictionary representing the chart trace.
        """
        
        selected_artist_id = self.artist_select.value
        if selected_artist_id is None:
            return {}
        selected_artist_name = self.artist_select.options[selected_artist_id]

        artist_over_time_data = self.data_manager.over_time_statistics.artist_over_time.get(selected_artist_id)
        if artist_over_time_data is None:
            return {}

        start_date = self.data_manager.static_data_metadata.data_date_range.start
        end_date = self.data_manager.static_data_metadata.data_date_range.end
        
        date_range = pl.date_range(
            start=start_date,
            end=end_date,
            interval="1mo",
            closed="both",
            eager=True,
        )
        
        x_values = [d.strftime("%Y-%m") for d in date_range]
        y_values = [artist_over_time_data.get(x, 0) / 3600000 for x in x_values]

        return {
            "x": x_values,
            "y": y_values,
            "type": "bar",
            "name": selected_artist_name,
        }

    async def get_artist_top_tracks_info(self):
        """
        Updates the top five labels for the selected artist with the most played tracks.

        If the data manager has no data, it will clear the labels.

        Otherwise, it will group the data by track name and artist, sum the milliseconds played,
        sort the data by the sum of milliseconds played in descending order,
        limit it to the top five tracks, and then update the labels with the track name and play time.
        """
        
        selected_artist_id = self.artist_select.value
        if selected_artist_id is None:
            return []

        async with self.data_manager.async_session() as session:
            stmt = (
                select(
                    ListeningEvent.track_id,
                    Track.track_name,
                    sql_func.sum(ListeningEvent.milliseconds_played).label("duration"),
                )
                .join(Track, ListeningEvent.track_id == Track.track_id)
                .join(track_artist, Track.track_id == track_artist.c.track_id)
                .filter(track_artist.c.artist_id == selected_artist_id)
                .group_by(ListeningEvent.track_id)
                .order_by(sql_func.sum(ListeningEvent.milliseconds_played).desc())
                .limit(self.top_tracks_limit)
            )
            result = await session.execute(stmt)
            data = result.all()
        
        self.top_tracks_info = [(row.track_id, row.track_name, row.duration) for row in data]

    def update_artist_top_songs_list(self):
        artist_track_songs = self.top_tracks_info
        for list_item, (_, track_name, _) in zip(self.top_tracks_name_labels, artist_track_songs):
            list_item.set_text(track_name)
        for list_item, (_, _, duration_in_milliseconds) in zip(self.top_tracks_duration_labels, artist_track_songs):
            duration_in_seconds = round(duration_in_milliseconds / 1000)
            hours, remainder = divmod(duration_in_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            list_item.set_text(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    async def on_top_song_list_item_click(self, index, event):
        track_id, track_name, _ = self.top_tracks_info[index]
        await self.emit_event(EventType.ANALYSE_TRACK_REQUEST, track_id=track_id)
        ui.notify(f"Switching to Analyse Track: {track_name}")

    def create_artist_top_songs_list(self):
        self.top_tracks_name_labels: list[ui.item_label] = []
        self.top_tracks_duration_labels: list[ui.item_label] = []
        with ui.list() as ui_list:
            for i in range(self.top_tracks_limit):
                with ui.item(on_click=partial(self.on_top_song_list_item_click, i)) as item:
                    with ui.item_section().props("slot=left side"):
                        ui.item_label(f"{i+1}.").bind_visibility_from(self.artist_select, "value", lambda value: value is not None)
                    with ui.item_section():
                        label = ui.item_label()
                        self.top_tracks_name_labels.append(label)
                    with ui.item_section():
                        label = ui.item_label()
                        self.top_tracks_duration_labels.append(label)

    async def create_widget(self, *args, **kwargs):
        with ui.column() as widget:
            self.artist_select = ui.select(
                await self.get_artist_names(),
                label="Artist",
                with_input=True,
                on_change=self.on_artist_change,
            )
            with ui.grid(rows=1, columns=r"100%").classes("w-dvw"):
                self.artist_over_time_plot.create_widget()
            self.create_artist_top_songs_list()
        return widget
