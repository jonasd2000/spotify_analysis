import humanize
import polars as pl
from nicegui import ui
from sqlalchemy import select

from data_labels import DataLabels
from data.models import Artist

from .plots import Plot
from .list import LabelList
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

class ArtistTopSongsList(LabelList):
    async def on_event(self, event_type, *args, **kwargs):
        await super().on_event(event_type, *args, **kwargs)
        match event_type:
            case EventType.DATA_ADDED:
                self.update()
            case EventType.ARTIST_SELECTED:
                self.update()
            case _:
                pass


class ArtistAnalysisWidget(DataWidget):
    """
    Widget for artist analysis.
    """

    artist_over_time_plot: Plot
    artist_top_five: LabelList

    def __init__(self, data_manager, parent=None):
        super().__init__(data_manager, parent)

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
        self.artist_top_five = ArtistTopSongsList(
            length=5,
            text=(self.get_artist_top_songs_labels, {}),
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

    def get_artist_top_songs_labels(self):
        """
        Updates the top five labels for the selected artist with the most played tracks.

        If the data manager has no data, it will clear the labels.

        Otherwise, it will group the data by track name and artist, sum the milliseconds played,
        sort the data by the sum of milliseconds played in descending order,
        limit it to the top five tracks, and then update the labels with the track name and play time.
        """
        
        if self.data_manager.has_listening_history_data:
            return ["" for _ in range(len(self.artist_top_five))]

        selected_artist = self.artist_select.value

        # filter the data for the selected artist
        # group it by track name and artist
        # and sum the milliseconds played
        # then sort the data by the sum of milliseconds played in descending order
        artist_filter = (pl.col(DataLabels.ARTIST.value) == selected_artist) if selected_artist is not None else (pl.col(DataLabels.ARTIST.value).is_null())
        
        data = (
            self.data_manager.streaming_data.filter(
                artist_filter
            )
            .group_by(
                DataLabels.TRACK_NAME.value,
                DataLabels.ARTIST.value,
            )
            .agg(pl.sum(DataLabels.MILLISECONDS_PLAYED.value))
            .sort(DataLabels.MILLISECONDS_PLAYED.value, descending=True)
            .with_columns(  # convert milliseconds to human readable time
                pl.duration(
                    milliseconds=pl.col(DataLabels.MILLISECONDS_PLAYED.value)
                ).alias("duration")
            )
            .limit(len(self.artist_top_five))
        )
        
        return [f"{i + 1}. {row[DataLabels.TRACK_NAME.value]} ({humanize.precisedelta(row['duration'], format='%0.0f')})" for i, row in enumerate(data.iter_rows(named=True))]

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
                # self.artist_top_five.create_widget()
        return widget
