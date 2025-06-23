from nicegui import ui

from .widget import Widget


class ArtistAnalysisWidget(Widget):
    top_graph_layouts = {
        "plot_bgcolor": "#E5ECF6",
        "xaxis": {"fixedrange": True, "showticklabels": False},
        "yaxis": {
            "fixedrange": True,
            "gridcolor": "white",
            "title": {"text": "Hours Played"},
        },
    }
    top_graph_config = {
        "responsive": True,
        "displayModeBar": False,
    }

    selected_artist = None

    def on_event(self, name, *args, propagate=True, **kwargs):
        match name:
            case "data_change":
                self.on_data_change()
            case _:
                pass
        return super().on_event(name, *args, propagate=propagate, **kwargs)

    def on_data_change(self):
        self.artist_select.set_options(self.get_artist_names())

    def get_artist_names(self):
        if self.data_manager.streaming_data.is_empty():
            return []
        return (
            self.data_manager.streaming_data["master_metadata_album_artist_name"]
            .drop_nulls()
            .unique()
            .to_list()
        )

    def on_artist_change_forward(self, select_artist: str) -> str:
        """
        Called when the artist_select widget is changed.
        Sets the value of self.selected_artist.
        """
        return select_artist

    def on_artist_change_backward(self, self_artist: str) -> str:
        """
        Called when the selected_artist attribute of this widget is changed.
        Sets the value of the self.artist_select widget.
        """
        return self_artist

    def create_artist_over_time_trace(self):
        if self.data_manager.streaming_data.is_empty():
            return None

    def create_artist_over_time_plot(self):
        trace = self.create_artist_over_time_trace()
        fig = {
            "data": [
                trace,
            ],
            "layout": self.top_graph_layouts,
            "config": self.top_graph_config,
        }

        self.artist_over_time_chart = ui.plotly(fig)

        return self.artist_over_time_chart

    def create_widget(self, *args, **kwargs):
        with ui.column() as widget:
            self.artist_select = ui.select(
                self.get_artist_names(),
                label="Artist",
                with_input=True,
            ).bind_value(
                self,
                "selected_artist",
                forward=self.on_artist_change_forward,
                backward=self.on_artist_change_backward,
            )
            with ui.grid(rows=1, columns=r"100%").classes("w-dvw"):
                self.create_artist_over_time_plot()
        return widget
