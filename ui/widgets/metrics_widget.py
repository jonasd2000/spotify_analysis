import logging

from nicegui import ui
from sqlalchemy import func as sql_func, select, case

from data.models import ListeningEvent, Track, track_artist

from .widget import DataWidget
from .plots import Plot
from .events import EventType


logger = logging.getLogger(__name__)


class MetricsWidget(DataWidget):
    diversity_data: dict[str, float]
    
    def __init__(self, data_manager, parent=None):
        super().__init__(data_manager, parent)

        self.diversity_data = None

        self.diversity_plot = Plot(
            trace=(self.create_diversity_trace, {}),
            layout={
                "plot_bgcolor": "#E5ECF6",
                "xaxis": {"fixedrange": True},
                "yaxis": {
                    "fixedrange": True,
                    "gridcolor": "white",
                    "title": {"text": "Diversity Score"},
                },
            },
            config={
                "responsive": True,
                "displayModeBar": False,
            },
            parent=self
        )

    async def on_event(self, event_type, *args, **kwargs):
        if event_type == EventType.DATA_ADDED:
            self.diversity_data = await self.get_diversity_data()
            self.diversity_plot.update()
        await super().on_event(event_type, *args, **kwargs)

    async def get_diversity_data(self):
        logger.debug("Getting diversity data...")
        # artist_month: sum ms per artist per YYYY-MM
        artist_month = (
            select(
                sql_func.strftime("%Y-%m", ListeningEvent.timestamp).label("ym"),
                track_artist.c.artist_id.label("artist_id"),
                sql_func.sum(ListeningEvent.milliseconds_played).label("artist_ms"),
            )
            .select_from(ListeningEvent)
            .join(Track, Track.track_id == ListeningEvent.track_id)
            .join(track_artist, Track.track_id == track_artist.c.track_id)
            .group_by(sql_func.strftime("%Y-%m", ListeningEvent.timestamp), track_artist.c.artist_id)
            .cte("artist_month")
        )

        # rank artists per month
        ranked = (
            select(
                artist_month.c.ym,
                artist_month.c.artist_id,
                artist_month.c.artist_ms,
                sql_func.row_number().over(
                    partition_by=artist_month.c.ym,
                    order_by=artist_month.c.artist_ms.desc()
                ).label("rn"),
            )
            .select_from(artist_month)
            .cte("ranked")
        )

        # sum top N (here N=5) per month
        top_n = (
            select(
                ranked.c.ym,
                sql_func.sum(case((ranked.c.rn <= 5, ranked.c.artist_ms), else_=0)).label("top_n_ms"),
            )
            .group_by(ranked.c.ym)
            .cte("top_n")
        )

        # total ms per month
        month_totals = (
            select(
                artist_month.c.ym,
                sql_func.sum(artist_month.c.artist_ms).label("total_ms"),
            )
            .group_by(artist_month.c.ym)
            .cte("month_totals")
        )

        # final diversity = (total - top_n) / top_n  (0 if top_n == 0)
        stmt = (
            select(
                month_totals.c.ym,
                case(
                    (top_n.c.top_n_ms > 0, (month_totals.c.total_ms - top_n.c.top_n_ms) / top_n.c.top_n_ms),
                    else_=0,
                ).label("diversity"),
            )
            .select_from(month_totals.outerjoin(top_n, month_totals.c.ym == top_n.c.ym))
            .order_by(month_totals.c.ym)
        )

        logger.debug(f"Executing diversity statement: {stmt}")
        async with self.data_manager.async_session() as session:
            res = await session.execute(stmt)
            rows = res.fetchall()  # list of (ym, diversity)
            
        self.diversity_data = {row[0]: row[1] for row in rows}
        logger.debug(f"diversity data: {self.diversity_data}")

    def create_diversity_trace(self, *args, **kwargs):
        if self.diversity_data is None:
            logger.warning("No data for diversity plot")
            return {}
        return {
            "x": tuple(self.diversity_data.keys()),
            "y": tuple(self.diversity_data.values()),
            "type": "line", 
            "name": "diversity"
        }

    async def create_widget(self, *args, **kwargs):
        logger.debug("Creating metrics widget...")
        await self.get_diversity_data()
        with ui.column() as widget:
            with ui.grid(rows=1, columns=r"100%").classes("w-dvw"):
                self.diversity_plot.create_widget()
        return widget
