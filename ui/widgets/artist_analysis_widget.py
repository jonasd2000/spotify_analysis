from nicegui import ui

from .widget import Widget


class ArtistAnalysisWidget(Widget):
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

    def on_artist_change(self, event):
        artist = event.value
        ui.notify(f"Selected artist: {artist}")

    def create_widget(self, *args, **kwargs):
        with ui.column() as widget:
            self.artist_select = ui.select(
                self.get_artist_names(),
                label="Artist",
                on_change=self.on_artist_change,
            )
        return widget
