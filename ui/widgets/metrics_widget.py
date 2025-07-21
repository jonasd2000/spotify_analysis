from nicegui import ui

from .widget import DataWidget
from .plots import Plot

class MetricsWidget(DataWidget):
    def create_widget(self, *args, **kwargs):
        with ui.column() as widget:
            diversity_plot = Plot(
                trace={"x": [1, 2, 3], "y": [2, 4, 5], "type": "line", "name": "diversity"},
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
                }, parent=self)
            diversity_plot.create_widget()
        return widget