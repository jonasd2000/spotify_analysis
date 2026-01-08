from typing import Callable, Dict, Tuple

from nicegui import ui

from .widget import Widget, UpdatableMixin
from .events import EventType


class Plot(Widget, UpdatableMixin):
    """
    Single plot object.

    Parameters
    ----------
    trace: Dict | Tuple[Callable, Dict]
        Plotly trace.
        If it is a callable, it is called with the kwargs in the second element of the tuple.
        The callable must return a Plotly trace.
    layout: Dict
        Plotly layout.
    config: Dict
        Plotly config.
    """

    _trace: Dict | Tuple[Callable, Dict]
    layout: Dict
    config: Dict

    fig: Dict
    plotly: ui.plotly

    def __init__(self, trace: Dict | Tuple[Callable, Dict], layout: Dict, config: Dict, parent=None):
        super().__init__(parent)
        self._trace = trace
        self.layout = layout
        self.config = config
        
        self.fig = None
        self.plotly = None

    async def on_event(self, event_type: EventType, *args, **kwargs):
        match event_type:
            case EventType.DATA_ADDED:
                self.update()
            case _:
                pass

    @property
    def was_created(self) -> bool:
        """
        Whether the plot has been created.

        The plot is created when the `create` method is called.

        Returns
        -------
        bool
            Whether the plot has been created.
        """

        return self.fig is not None and self.plotly is not None

    def get_trace(self) -> Dict:
        """
        Get the trace data.

        If self._trace is a dict, it is returned directly.
        If self._trace is a tuple, the first element is called with the kwargs in the second element
        and the result is returned.

        Returns
        -------
        Dict
            The trace data.
        """
        return (
            self._trace
            if isinstance(self._trace, dict)
            else self._trace[0](**self._trace[1])
        )

    def on_update(self) -> None:
        """
        Update the plot with the latest trace data.

        This function is used to update the plot whenever the trace data changes.
        It should be called after updating the trace data.
        """
        trace = self.get_trace()
        self.fig["data"][0] = trace
        self.plotly.update()

    def create_widget(self) -> ui.plotly:
        """
        Create the plotly figure.

        Returns
        -------
        ui.plotly
            The figure as a nicegui plotly object.
        """
        trace = self.get_trace()
        fig = {
            "data": [
                trace,
            ],
            "layout": self.layout,
            "config": self.config,
        }

        plotly = ui.plotly(fig)

        self.fig = fig
        self.plotly = plotly

        return self.plotly


class PlotCollection:
    """
    Collection of plots with common layout and config.
    """

    plots: Dict[str, Plot]
    layout: Dict
    config: Dict

    def __init__(self, layout: Dict, config: Dict):
        self.plots = {}
        self.layout = layout
        self.config = config

    def update_plots(self) -> None:
        for plot_name, plot in self.plots.items():
            plot.update()

    def add_plot(self, name: str, plot: Plot) -> None:
        self.plots[name] = plot

    def add_plot_from_trace(
        self, name: str, trace: Dict | Tuple[Callable, Dict], parent=None
    ) -> None:
        plot = Plot(trace, self.layout, self.config, parent)
        self.add_plot(name, plot)

    def create_plot(self, name: str) -> ui.plotly:
        return self.plots[name].create_widget()
