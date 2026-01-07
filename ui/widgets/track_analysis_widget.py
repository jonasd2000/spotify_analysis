import datetime

import humanize
import polars as pl
from nicegui import ui
from nicegui.events import ValueChangeEventArguments
from sqlalchemy import select

from data.models import Track, Artist, track_artist

from .plots import Plot
from .widget import DataWidget
from .events import EventType


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

    def __init__(self, data_manager, parent=None):
        super().__init__(data_manager, parent)

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
            case _:
                pass

    async def on_data_change(self):
        """
        Called when the 'data_change' event is received.
        Resets the track select widget, the top five tracks labels, and updates the track over time plot.
        """
        self.track_select.set_options(await self.get_track_names())

    async def get_track_names(self) -> dict[int, str]:
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

    async def on_track_change(self, event: ValueChangeEventArguments):
        """
        Called when the track_select widget is changed.
        Sets the value of self.selected_track.
        """
        selected_track_id = event.value
        
        await self.data_manager.get_track_over_time_statistics(selected_track_id)
        self.total_playtime_label.set_text(self.get_total_playtime_label_text())
        
        await self.emit_event(EventType.TRACK_SELECTED, propagate_upwards=False)

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
        
        selected_track_id = self.track_select.value
        if selected_track_id is None:
            return {}
        selected_track_name = self.track_select.options[selected_track_id]
        
        track_over_time_data = self.data_manager.over_time_statistics.track_over_time.get(selected_track_id)
        if track_over_time_data is None:
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
        y_values = [track_over_time_data.get(d, 0) / 3600000 for d in x_values]

        return {
            "x": x_values,
            "y": y_values,
            "type": "bar",
            "name": selected_track_name,
        }

    def get_total_playtime_label_text(self):
        selected_track_id = self.track_select.value
        if selected_track_id is None:
            return ""
        track_over_time_data = self.data_manager.over_time_statistics.track_over_time.get(selected_track_id)
        if track_over_time_data is None:
            return ""
        total_playtime = datetime.timedelta(milliseconds=sum(track_over_time_data.values()))
        return f"Total Playtime: {humanize.naturaldelta(total_playtime)}"

    async def create_widget(self, *args, **kwargs):
        with ui.column() as widget:
            self.track_select = ui.select(
                await self.get_track_names(),
                label="Track",
                with_input=True,
                on_change=self.on_track_change,
            )
            with ui.grid(rows=1, columns=r"100%").classes("w-dvw"):
                self.track_over_time_plot.create_widget()
            self.total_playtime_label = ui.label("")
        return widget
