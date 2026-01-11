import datetime
from functools import partial
import logging

import humanize
import polars as pl
from nicegui import ui
from nicegui.events import ValueChangeEventArguments
from sqlalchemy import select, func as sql_func

from data.models import Artist, ListeningEvent, track_artist, Track

from .plots import Plot
from .widget import DataWidget
from .events import EventType


logger = logging.getLogger(__name__)


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
    artist_over_time_cache: dict[int, dict[str, datetime.timedelta]]

    artist_over_time_plot: Plot

    def __init__(self, data_manager, parent=None):
        super().__init__(data_manager, parent)

        self.artist_over_time_cache = {}
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

    async def on_event(self, event_type: EventType, *args, **kwargs):
        match event_type:
            case EventType.DATA_ADDED:
                logger.debug("DATA_ADDED event received")
                await self.on_data_change()
            case EventType.ARTIST_SELECTED:
                logger.debug("ARTIST_SELECTED event received")
                if "artist_id" not in kwargs:
                    error = TypeError("artist_id kwarg required for ARTIST_SELECTED event")
                    logger.exception(error)
                    raise error
                artist_id = kwargs["artist_id"]
                await self.on_artist_selected(artist_id)
            case _:
                pass

    async def on_data_change(self):
        """
        Called when the 'data_change' event is received.
        """
        self.artist_select.set_options(await self.get_artist_names())
            
    async def on_artist_selected(self, artist_id: int):
        logger.info(f"Artist selected: {artist_id=}")
        await self.get_artist_over_time_stats(artist_id)
        await self.get_artist_top_tracks_info(artist_id)
        self.update_artist_top_songs_list()

    async def on_artist_select_widget_change(self, event: ValueChangeEventArguments) -> None:
        """
        Called when the artist_select widget is changed.
        Sets the value of self.selected_artist.
        """
        
        logger.debug("Artist Select widget changed...")
        artist_id = event.value
        await self.emit_event(EventType.ARTIST_SELECTED, propagate_upwards=False, artist_id=artist_id)

    async def get_artist_names(self) -> dict[int, str]:
        logger.debug("Getting artist names...")
        async with self.data_manager.async_session() as session:
            stmt = select(Artist.artist_id, Artist.artist_name).select_from(Artist).order_by(Artist.artist_name)
            result = await session.execute(stmt)
            artist_names = {
                row.artist_id: row.artist_name
                for row in result.all()
            }
            return artist_names

    async def get_artist_over_time_stats(self, artist_id: int, force_refresh: bool=False) -> None:
        logger.debug(f"Getting artist over time stats for {artist_id=}")
        if (
            artist_id in self.artist_over_time_cache
            and not force_refresh
        ):
            logger.debug(f"Artist over time stats already cached for {artist_id=}")
            return
        
        logger.debug(f"Getting artist over time stats for {artist_id=} from database...")
        async with self.data_manager.async_session() as session:
            stmt = (
                select(sql_func.strftime("%Y-%m", ListeningEvent.timestamp), sql_func.sum(ListeningEvent.milliseconds_played))
                .join(Track, Track.track_id == ListeningEvent.track_id)
                .join(track_artist, Track.track_id == track_artist.c.track_id)
                .filter(track_artist.c.artist_id == artist_id)
                .group_by(sql_func.strftime("%Y-%m", ListeningEvent.timestamp))
                .order_by(ListeningEvent.timestamp)
            )
            
            logger.debug(f"Executing artist over time statement: {stmt}")
            result = await session.execute(stmt)
            over_time_data = {
                month: datetime.timedelta(milliseconds=duration_in_ms)
                for month, duration_in_ms in result.all()
            }
            
            logger.debug(f"Artist over time stats for {artist_id=}: {over_time_data}")
            self.artist_over_time_cache[artist_id] = over_time_data

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
        
        logger.debug("Creating artist over time trace...")
        selected_artist_id = self.artist_select.value
        if selected_artist_id is None:
            logger.debug("Artist Select widget value is None")
            return {}
        selected_artist_name = self.artist_select.options[selected_artist_id]

        artist_over_time_data = self.artist_over_time_cache.get(selected_artist_id)
        if artist_over_time_data is None:
            logger.warning(f"No data for {selected_artist_id=} available")
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
        duration_in_hours = [artist_over_time_data.get(x, datetime.timedelta(0)).total_seconds() / 3600 for x in x_values]

        logger.debug(f"Artist over time trace for {selected_artist_id=}: {x_values=}, {duration_in_hours=}")

        return {
            "x": x_values,
            "y": duration_in_hours,
            "type": "bar",
            "name": selected_artist_name,
        }

    async def get_artist_top_tracks_info(self, artist_id: int):
        """
        Updates the top five labels for the selected artist with the most played tracks.

        If the data manager has no data, it will clear the labels.

        Otherwise, it will group the data by track name and artist, sum the milliseconds played,
        sort the data by the sum of milliseconds played in descending order,
        limit it to the top five tracks, and then update the labels with the track name and play time.
        """
        logger.debug(f"Getting artist top tracks info for {artist_id=}")
        async with self.data_manager.async_session() as session:
            stmt = (
                select(
                    ListeningEvent.track_id,
                    Track.track_name,
                    sql_func.sum(ListeningEvent.milliseconds_played).label("duration"),
                )
                .join(Track, ListeningEvent.track_id == Track.track_id)
                .join(track_artist, Track.track_id == track_artist.c.track_id)
                .filter(track_artist.c.artist_id == artist_id)
                .group_by(ListeningEvent.track_id)
                .order_by(sql_func.sum(ListeningEvent.milliseconds_played).desc())
                .limit(self.top_tracks_limit)
            )
            
            logger.debug(f"Executing artist top tracks statement: {stmt}")
            result = await session.execute(stmt)
            data = result.all()
        
        self.top_tracks_info = [(row.track_id, row.track_name, row.duration) for row in data]

        logger.debug(f"Artist top tracks info for {artist_id=}: {self.top_tracks_info}")

    def update_artist_top_songs_list(self):
        logger.debug("Updating artist top songs list...")
        for list_item, (_, track_name, _) in zip(self.top_tracks_name_labels, self.top_tracks_info):
            list_item.set_text(track_name)
        for list_item, (_, _, duration_in_milliseconds) in zip(self.top_tracks_duration_labels, self.top_tracks_info):
            duration_in_seconds = round(duration_in_milliseconds / 1000)
            hours, remainder = divmod(duration_in_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            list_item.set_text(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    async def on_top_song_list_item_click(self, index, event):
        logger.debug(f"Top song list item {index} clicked")
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
        logger.debug("Creating artist analysis widget...")
        with ui.column() as widget:
            self.artist_select = ui.select(
                await self.get_artist_names(),
                label="Artist",
                with_input=True,
                on_change=self.on_artist_select_widget_change,
            )
            with ui.grid(rows=1, columns=r"100%").classes("w-dvw"):
                self.artist_over_time_plot.create_widget()
            self.create_artist_top_songs_list()
        return widget
