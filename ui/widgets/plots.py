from typing import Callable, Dict, Tuple

from nicegui import ui


class Plot:
    trace: Dict | Tuple[Callable, Dict]
    layout: Dict
    config: Dict

    fig: Dict
    plotly: ui.plotly

    def __init__(self, trace: Dict | Tuple[Callable, Dict], layout: Dict, config: Dict):
        self.trace = trace
        self.layout = layout
        self.config = config

    def get_trace(self) -> Dict:
        return (
            self.trace
            if isinstance(self.trace, dict)
            else self.trace[0](**self.trace[1])
        )

    def update(self) -> None:
        trace = self.get_trace()
        self.fig["data"][0] = trace
        self.plotly.update()

    def create(self) -> ui.plotly:
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
        self, name: str, trace: Dict | Tuple[Callable, Dict]
    ) -> None:
        self.add_plot(name, Plot(trace, self.layout, self.config))

    def create_plot(self, name: str) -> ui.plotly:
        return self.plots[name].create()
