import datetime

import humanize
from nicegui import element, ui
from nicegui.events import ValueChangeEventArguments, GenericEventArguments
from sqlalchemy import func as sql_func, select
from sqlalchemy.orm import selectinload

from data_manager import DateRange
from data.models import Base, Track, Artist, Podcast, ListeningEvent, Podcast, Audiobook

from .plots import PlotCollection
from .widget import DataWidget
from .events import EventType


class OverviewWidget(DataWidget):
    plots: PlotCollection
    filtered_date_range: DateRange | None
    
    top_playtime_item_limit: int = 10
    top_playtime_cache: dict[type[Base], list[tuple[Base, datetime.timedelta]]]
    unique_items_cache: dict[type[Base], int]
    total_playtime_cache: dict[type[Base], datetime.timedelta]

    def __init__(self, data_manager, parent=None):
        super().__init__(data_manager, parent)
        self.filtered_date_range = None
        
        self.top_playtime_cache = {}
        self.unique_items_cache = {}
        self.total_playtime_cache = {}
        
        self.setup_plots()

    def setup_plots(self):
        """
        Sets up the plots for this widget.

        Adds three plots to the PlotCollection:
        1. top_tracks: a bar chart of the top 10 tracks by hours played, with a hovertemplate that shows the track name and artist.
        2. top_artists: a bar chart of the top 10 artists by hours played.
        3. top_podcasts: a bar chart of the top 10 podcasts by hours played.
        """
        
        self.plots = PlotCollection(
            layout={
                "plot_bgcolor": "#E5ECF6",
                "xaxis": {
                    "fixedrange": True,
                    "gridcolor": "white",
                    "title": {"text": "Hours Played"},
                },
                "yaxis": {"fixedrange": True, "showticklabels": False},
            },
            config={
                "responsive": True,
                "displayModeBar": False,
            },
        )
        self.plots.add_plot_from_trace(
            name="top_tracks",
            trace=(
                self.get_top_chart_trace,
                {
                    "media_type_model": Track,
                    "attribute_getters": [
                        lambda t: t.track_name, # get track name
                        lambda t: ", ".join(artist.artist_name for artist in t.artists) # get artist names as a comma-separated string
                    ],
                    "limit": 10,
                    "hovertemplate": r"<b>%{text}</b> - %{customdata[1]}<br><extra>Played for %{customdata[0]}</extra>",
                },
            ),
            parent=self,
        )
        self.plots.add_plot_from_trace(
            name="top_artists",
            trace=(
                self.get_top_chart_trace,
                {
                    "media_type_model": Artist,
                    "attribute_getters": [lambda a: a.artist_name],
                    "limit": 10,
                    "hovertemplate": None,
                },
            ),
            parent=self,
        )
        self.plots.add_plot_from_trace(
            name="top_podcasts",
            trace=(
                self.get_top_chart_trace,
                {
                    "media_type_model": Podcast,
                    "attribute_getters": [lambda p: p.podcast_name],
                    "limit": 10,
                    "hovertemplate": None,
                },
            ),
            parent=self,
        )

    async def on_event(self, event_type: EventType, *args, **kwargs):
        match event_type:
            case EventType.DATA_ADDED:
                await self.on_data_change()
            case _:
                pass

        await super().on_event(event_type, *args, **kwargs)

    async def on_data_change(self):
        """
        Called when the 'data_change' event is received.
        Resets the date range widgets and updates all plots.
        """
        await self.refresh_stats()
        self.plots.update_plots()
        
    async def refresh_stats(self):
        await self.get_top_playtime_stats()
        await self.get_unique_items_stats()
        await self.get_total_playtime()

    async def get_top_playtime_stats(self) -> None:
        date_range = self.filtered_date_range or self.data_manager.static_data_metadata.data_date_range
        date_range_filter = ListeningEvent.timestamp.between(date_range.start, date_range.end)

        playtime = sql_func.sum(ListeningEvent.milliseconds_played)
        media_type_select_options = {
            Track: [selectinload(Track.artists)],
        }
        
        async with self.data_manager.async_session() as session:
            for media_type_model in [Track, Artist, Podcast]:
                options = media_type_select_options.get(media_type_model, [])
                top_stmt = self.data_manager.build_top_stmt(
                    media_type_model,
                    by=playtime,
                    limit=self.top_playtime_item_limit,
                    filters=[date_range_filter],
                    options=options,
                )
                
                result = await session.execute(top_stmt)
                items = list(reversed(result.all()))
                items_with_timedelta = [
                    (media_type, datetime.timedelta(milliseconds=ms_played))
                    for media_type, ms_played in items
                ]
                
                self.top_playtime_cache[media_type_model] = items_with_timedelta

    async def get_unique_items_stats(self) -> None:
        date_range = self.filtered_date_range or self.data_manager.static_data_metadata.data_date_range
        date_range_filter = ListeningEvent.timestamp.between(date_range.start, date_range.end)
        
        async with self.data_manager.async_session() as session:
            for media_type_model in [Track, Artist, Podcast]:
                unique_stmt = self.data_manager.build_unique_stmt(media_type_model, filters=[date_range_filter])
                result = await session.execute(unique_stmt)
                unique_count = result.scalar_one()
                self.unique_items_cache[media_type_model] = unique_count

    async def get_total_playtime(self):
        date_range = self.filtered_date_range or self.data_manager.static_data_metadata.data_date_range
        date_range_filter = ListeningEvent.timestamp.between(date_range.start, date_range.end)
        
        total_playtime_stmt = (
            select(sql_func.sum(ListeningEvent.milliseconds_played))
            .filter(ListeningEvent.timestamp.between(date_range.start, date_range.end))
            .select_from(ListeningEvent)
        )
        
        media_type_where_stmts = {
            Track: ListeningEvent.track_id != None,
            Podcast: ListeningEvent.podcast_episode_id != None,
            Audiobook: ListeningEvent.audiobook_chapter_id != None
        }
        
        async with self.data_manager.async_session() as session:
            for media_type, where_stmt in media_type_where_stmts.items():
                media_type_total_playtime_stmt = total_playtime_stmt.where(where_stmt)
                result = await session.execute(media_type_total_playtime_stmt)
                total_playtime = result.scalar_one()
                if total_playtime is not None:
                    total_playtime = datetime.timedelta(milliseconds=total_playtime)
                self.total_playtime_cache[media_type] = total_playtime

    @staticmethod
    def _get_chart_trace(x, y, text) -> dict:
        """
        Generates a horizontal bar chart trace.

        Parameters
        ----------
        x : list
            The list of names of the items (e.g. track names, artist names, etc.)
        y : list
            The list of values for each item (e.g. playtime, number of plays, etc.)
        text : list
            The list of text to display on the bars of the chart.

        Returns
        -------
        dict
            The trace dictionary.
        """
        return {
            "type": "bar",
            "name": "Top Tracks",
            "orientation": "h",
            "x": y,
            "y": x,
            "text": text,
            "textposition": "inside",
            "insidetextanchor": "start",
        }

    def get_top_chart_trace(
        self, media_type_model, attribute_getters, hovertemplate=None, limit=10
    ) -> dict:
        """
        Generates a chart trace for the top features by playtime.

        Parameters
        ----------
        feature : str
            The primary feature to group by for the chart (e.g., track name, artist name).
        media_type : str
            The type of media to filter the data by (e.g., track, episode).
        hovertemplate : str, optional
            The template string for the hover labels. Defaults to a template showing the feature name and playtime.
        additional_features : list, optional
            Additional features to include in the custom data for hover labels.
        limit : int, optional
            The number of top features to include in the trace. Defaults to 10.

        Returns
        -------
        Dict
            A dictionary representing the chart trace.
        """

        most_listened_to_instances_of_media_type = self.top_playtime_cache[media_type_model][:limit]

        main_attribute, *additional_attribute_getters = attribute_getters

        feature_names = [main_attribute(instance) for instance, _ in most_listened_to_instances_of_media_type]

        timedeltas = [timedelta for _, timedelta in most_listened_to_instances_of_media_type]
        hours_played = [td.total_seconds() / 3600 for td in timedeltas]

        trace = self._get_chart_trace(x=feature_names, y=hours_played, text=feature_names)
        hovertemplate = hovertemplate or r"%{text}<br><extra>Played for %{customdata[0]}</extra>"
        
        trace.update(
            hovertemplate=hovertemplate,
            customdata=[
                (humanize.precisedelta(td, suppress=["days"], format="%0.0f"), *f)
                for td, *f in zip(
                    timedeltas,
                    *[[attribute_getter(instance) for instance, _ in most_listened_to_instances_of_media_type] for attribute_getter in additional_attribute_getters],
                )
            ],
        )

        return trace

    async def on_date_range_filter_change(self, event: ValueChangeEventArguments) -> None:
        value: dict[str, int] = event.value
        
        range_min_days, range_max_days = value["min"], value["max"]
        
        if self.data_manager.static_data_metadata.data_date_range is None:
            return
        
        data_min_date = self.data_manager.static_data_metadata.data_date_range.start
        
        min_date = data_min_date.date() + datetime.timedelta(days=range_min_days)
        max_date = data_min_date.date() + datetime.timedelta(days=range_max_days)
        
        # set the filtered date range and refresh the stats
        self.filtered_date_range = DateRange(min_date, max_date)
        
    async def on_date_range_filter_change_release(self, event: GenericEventArguments) -> None:
        await self.refresh_stats()
        self.plots.update_plots()

    async def reset_date_range_widget(self):
        """
        Resets the date range widget.
        Gets the earliest and latest dates from the data manager, and sets the date range to the range between the two.
        If the data is empty, does nothing.
        """

        if self.data_manager.static_data_metadata.data_date_range is None:
            return

        data_start_date = self.data_manager.static_data_metadata.data_date_range.start
        data_end_date = self.data_manager.static_data_metadata.data_date_range.end

        days = (data_end_date - data_start_date).days
        
        self.date_range_widget.max = days
        self.date_range_widget.value = {"min": 0, "max": days}
        await self.on_date_range_filter_change_release(None)  # type: ignore

    def create_date_range_filter_controls(self):
        """
        Initializes and configures the date range controls for the widget.

        This method sets up a range widget for selecting a time span, binding its
        visibility and value to the streaming data availability and current date range.
        It also sets up a label to display the selected date range.

        The range widget's visibility is controlled by the presence of streaming data
        and its value is synchronized with the date_range attribute, allowing for both
        forward and backward transformations.

        The method also ensures that the date range widget is reset to the correct
        initial state by calling reset_date_range_widget.
        """

        # create the range widget
        self.date_range_widget = ui.range(
            min=0, max=1, 
            value={"min": 0, "max": 1}, 
            on_change=self.on_date_range_filter_change
        ).on('change', self.on_date_range_filter_change_release).classes("w-dvw")

        # the label that displays the selected date range
        ui.label("").bind_text_from(
            target_object=self,
            target_name="filtered_date_range",
            backward=lambda v: f"From {v.start if v else ''} to {v.end if v else ''}.",
        ).classes("w-dvw")

    def total_music_play_time_label_text(self, total_music_playtime: datetime.timedelta) -> str:
        return f"The total time you spent listening to music is {humanize.naturaldelta(total_music_playtime)}."
    
    def total_podcast_time_label_text(self, total_podcast_playtime: datetime.timedelta) -> str:
        return f"The time you spent listening to podcasts is {humanize.naturaldelta(total_podcast_playtime)}."

    def unique_tracks_label_text(self, unique_tracks: int):
        return f"You listened to {unique_tracks} unique tracks during this period."

    def unique_artists_label_text(self, unique_artists: int):
        return f"You listened to {unique_artists} unique artists during this period."
    
    def unique_podcasts_label_text(self, unique_podcasts: int):
        return f"You listened to {unique_podcasts} unique podcasts during this period."

    def create_music_analysis_section(self):
        ui.markdown("## Music Analysis")
        # Total music play time label
        ui.label("").bind_text_from(
            self, "total_playtime_cache",
            backward=lambda playtime_cache: self.total_music_play_time_label_text(
                playtime_cache.get(Track, datetime.timedelta(0))
            ),
        )
        with ui.grid(rows=1, columns=r"50% 50%").classes("w-dvw"):
            with ui.column():  # Top tracks plot and unique tracks label
                self.plots.create_plot("top_tracks")

                # Unique tracks label
                self.unique_tracks_label = ui.label("").bind_text_from(
                    self, "unique_items_cache",
                    backward=lambda unique_items_cache: self.unique_tracks_label_text(
                        unique_items_cache.get(Track, 0)
                    ),
                )
            with ui.column():  # Top artists plot and unique artists label
                self.plots.create_plot("top_artists")

                # Unique artists label
                self.unique_artists_label = ui.label("").bind_text_from(
                    self, "unique_items_cache",
                    backward=lambda unique_items_cache: self.unique_artists_label_text(
                        unique_items_cache.get(Artist, 0)
                    ),
                )

    def create_podcast_analysis_section(self):
        ui.markdown("## Podcast Analysis")

        # Total podcast play time label
        ui.label("").bind_text_from(
            self, "total_playtime_cache",
            backward=lambda playtime_cache: self.total_podcast_time_label_text(
                playtime_cache.get(Podcast, datetime.timedelta(0))
            ),
        )
        with ui.grid(rows=1, columns=r"50% 50%").classes("w-dvw"):
            with ui.column():
                self.plots.create_plot("top_podcasts")

                # Unique podcasts label
                self.unique_podcasts_label = ui.label("").bind_text_from(
                    self, "unique_items_cache",
                    backward=lambda unique_items_cache: self.unique_podcasts_label_text(
                        unique_items_cache.get(Podcast, 0)
                    ),
                )

    async def create_widget(self, *args, **kwargs) -> element.Element:
        await self.refresh_stats()
        
        ui.label("No data loaded").bind_visibility_from(
            self.data_manager.static_data_metadata, "has_listening_history_data", lambda has_data: not has_data
        )
        with ui.column().bind_visibility_from(
            self.data_manager.static_data_metadata, "has_listening_history_data"
        ) as widget:
            self.create_date_range_filter_controls()
            self.create_music_analysis_section()
            self.create_podcast_analysis_section()

        await self.reset_date_range_widget()

        return widget
