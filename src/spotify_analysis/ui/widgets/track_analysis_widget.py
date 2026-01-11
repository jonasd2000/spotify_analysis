import datetime
import logging

import humanize
import polars as pl
from nicegui import ui
from nicegui.events import ValueChangeEventArguments
from sqlalchemy import select, func as sql_func

from spotify_analysis.data.models import Track, Artist, track_artist, ListeningEvent

from .plots import Plot
from .widget import DataWidget
from .events import EventType


logger = logging.getLogger(__name__)


class TrackOverTimePlot(Plot):
    async def on_event(self, event_type, *args, **kwargs):
        await super().on_event(event_type, *args, **kwargs)
        match event_type:
            case EventType.TRACK_SELECTED:
                self.update()
            case _:
                pass

class TrackAnalysisWidget(DataWidget):
    """
    Widget for track analysis.
    """

    track_over_time_plot: Plot
    
    track_over_time_cache: dict[int, dict[str, datetime.timedelta]]

    def __init__(self, data_manager, parent=None):
        super().__init__(data_manager, parent)

        self.track_over_time_cache = {}

        # track over time plot initialisation
        self.track_over_time_plot = TrackOverTimePlot(
            trace=(self.create_track_over_time_trace, {}),
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
                await self.on_data_change()
            case EventType.TRACK_SELECTED:
                if "track_id" not in kwargs:
                    error = TypeError("track_id kwarg required for TRACK_SELECTED event")
                    logger.exception(error)
                    raise error
                track_id = kwargs["track_id"]
                await self.on_track_selected(track_id)
            case _:
                pass

    async def on_data_change(self):
        """
        Called when the 'data_change' event is received.
        Resets the track select widget, the top five tracks labels, and updates the track over time plot.
        """
        self.track_select.set_options(await self.get_track_names())

    async def on_track_selected(self, track_id: int):
        logger.info(f"Track selected: {track_id}")
        await self.get_track_over_time_stats(track_id)
        self.total_playtime_label.set_text(self.get_total_playtime_label_text())

    async def on_track_select_widget_change(self, event: ValueChangeEventArguments):
        """
        Called when the track_select widget is changed.
        Sets the value of self.selected_track.
        """
        
        track_id = event.value
        await self.emit_event(EventType.TRACK_SELECTED, propagate_upwards=False, track_id=track_id)

    async def get_track_names(self) -> dict[int, str]:
        logger.debug("Getting track names...")
        async with self.data_manager.async_session() as session:
            stmt = (
                select(Track.track_id, Track.track_name, Artist.artist_name)
                .select_from(Track)
                .join(track_artist, Track.track_id == track_artist.c.track_id)
                .join(Artist, Artist.artist_id == track_artist.c.artist_id)
            )
            result = await session.execute(stmt)
            track_names = {
                row.track_id: f"{row.track_name} - {row.artist_name}"
                for row in result.all()
            }
            return track_names

    async def get_track_over_time_stats(self, track_id: int, force_refresh: bool=False) -> None:
        logger.debug(f"Getting track over time stats for {track_id=}")
        if (
            track_id in self.track_over_time_cache 
            and not force_refresh
        ):
            logger.debug(f"Track over time stats already cached for {track_id=}")
            return
        
        logger.debug(f"Getting track over time stats for {track_id=} from database...")
        async with self.data_manager.async_session() as session:
            stmt = (
                select(sql_func.strftime("%Y-%m", ListeningEvent.timestamp), sql_func.sum(ListeningEvent.milliseconds_played))
                .filter(ListeningEvent.track_id == track_id)
                .group_by(sql_func.strftime("%Y-%m", ListeningEvent.timestamp))
                .order_by(ListeningEvent.timestamp)
            )
            
            logger.debug(f"Executing track over time statement: {stmt}")
            result = await session.execute(stmt)
            over_time_data: dict[str, int] = {
                month: datetime.timedelta(milliseconds=duration_in_ms)
                for month, duration_in_ms in result.all()
            }
            
            logger.debug(f"Track over time stats for {track_id=}: {over_time_data}")
            self.track_over_time_cache[track_id] = over_time_data

    def create_track_over_time_trace(self):
        """
        Generates a chart trace for the hours played of the selected track over time.

        Parameters
        ----------
        None

        Returns
        -------
        Dict
            A dictionary representing the chart trace.
        """
        
        logger.debug("Creating track over time trace...")
        selected_track_id = self.track_select.value
        if selected_track_id is None:
            logger.debug("Track Select widget value is None")
            return {}
        selected_track_name = self.track_select.options[selected_track_id]
        
        track_over_time_data = self.track_over_time_cache.get(selected_track_id)
        if track_over_time_data is None:
            logger.warning(f"No data for {selected_track_id=} available")
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
        duration_in_hours = [track_over_time_data.get(d, datetime.timedelta(0)).total_seconds() / 3600 for d in x_values]

        logger.debug(f"Track over time trace for {selected_track_id=}: {x_values=}, {duration_in_hours=}")

        return {
            "x": x_values,
            "y": duration_in_hours,
            "type": "bar",
            "name": selected_track_name,
        }

    def get_total_playtime_label_text(self):
        logger.debug("Getting total playtime label text...")
        selected_track_id = self.track_select.value
        if selected_track_id is None:
            return ""
        track_over_time_data = self.track_over_time_cache.get(selected_track_id)
        if track_over_time_data is None:
            return ""
        total_playtime = sum(track_over_time_data.values(), start=datetime.timedelta(0))
        return f"Total Playtime: {humanize.precisedelta(total_playtime, suppress=("days", "months"), format='%.0f')}"

    async def create_widget(self, *args, **kwargs):
        logger.debug("Creating track analysis widget...")
        with ui.column() as widget:
            self.track_select = ui.select(
                await self.get_track_names(),
                label="Track",
                with_input=True,
                on_change=self.on_track_select_widget_change,
            )
            with ui.grid(rows=1, columns=r"100%").classes("w-dvw"):
                self.track_over_time_plot.create_widget()
            self.total_playtime_label = ui.label("")
        return widget
