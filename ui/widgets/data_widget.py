from multiprocessing import Manager

from nicegui import run, ui

from data_manager import DataManager

from .widget import Widget


class DataWidget(Widget):
    """
    Widget for handling data loading and management.
    """

    def handle_multi_upload(self, event) -> None:
        """
        Called when a multiple file upload is completed.
        Appends the newly uploaded files to the data_manager and notifies all widgets of the change.
        """
        file_names, file_contents = event.names, event.contents
        self.data_manager.append_files(file_names, file_contents)

        self.on_event("data_change")

    def data_loaded_label_text(self) -> str:
        return (
            f"Data from {len(self.data_manager.files_loaded)} files loaded."
            if not self.data_manager.streaming_data.is_empty()
            else "No data loaded."
        )

    @staticmethod
    def audio_features_loaded_label_text(data_manager: DataManager) -> str:
        if data_manager.audio_features.is_empty():
            return "No audio features loaded."
        unique_track_ids = data_manager.get_unique_track_ids()
        intersection = set(data_manager.audio_features["id"]).intersection(
            unique_track_ids
        )
        return f"Loaded audio features cover {round(100 * len(intersection) / len(unique_track_ids), 2)}% of tracks in the data set."

    async def get_audio_features_callback(
        self, queue, progressbar, dialog, client_id, client_secret
    ):
        progressbar.visible = True
        audio_features = await run.cpu_bound(
            self.data_manager.get_audio_features_from_spotify,
            queue,
            spotify_client_id=client_id,
            spotify_client_secret=client_secret,
        )
        self.data_manager.audio_features = audio_features
        ui.notify("Audio Features loaded.")
        progressbar.visible = False
        dialog.close()

    def create_streaming_history_section(self):
        with ui.column():
            # streaming history info label
            with ui.label() as label:
                label.bind_text_from(
                    self, "data_manager", lambda dm: self.data_loaded_label_text()
                )
                with ui.tooltip() as tooltip:
                    tooltip.style("white-space: pre-wrap")
                    tooltip.bind_text_from(
                        self,
                        "data_manager",
                        lambda dm: "\n".join(sorted(dm.files_loaded)),
                    )
                    tooltip.bind_visibility_from(
                        self,
                        "data_manager",
                        lambda dm: not dm.streaming_data.is_empty(),
                    )
            # streaming history upload
            ui.upload(
                multiple=True,
                max_files=20,
                max_file_size=20_000_000,
                on_rejected=lambda e: ui.notification("upload failed"),
                on_multi_upload=lambda event: self.handle_multi_upload(event),
            )

    def create_audio_features_section(self):
        with ui.column():
            # audio features upload facility
            with ui.row():
                ui.label("Get Audio Features")

                # spotify api client info dialog
                with ui.dialog() as dialog, ui.card():
                    queue = Manager().Queue()
                    ui.timer(
                        0.1,
                        callback=lambda: progressbar.set_value(
                            queue.get() if not queue.empty() else progressbar.value
                        ),
                    )
                    client_id = ui.input(
                        label="Spotify API Client ID", placeholder="Your Client ID"
                    )
                    client_secret = ui.input(
                        label="Spotify API Client Secret",
                        placeholder="Your Client Secret",
                    )
                    with ui.row():
                        ui.button(
                            "Get Track Audio Features",
                            on_click=lambda: self.get_audio_features_callback(
                                queue,
                                progressbar,
                                dialog,
                                client_id.value,
                                client_secret.value,
                            ),
                        )
                        ui.button("Cancel", on_click=dialog.close)
                    progressbar = ui.circular_progress(value=0, max=100).props(
                        "instant-feedback"
                    )
                    progressbar.visible = False
            # audio features from file upload
            ui.button("From Spotify", on_click=dialog.open).bind_enabled_from(
                self.data_manager, "streaming_data", lambda x: not x.is_empty()
            )

            ui.upload(
                label="From File",
                on_upload=lambda e: self.data_manager.get_audio_features_from_file(e),
            )

            with ui.row():
                ui.label().bind_text_from(
                    self,
                    "data_manager",
                    lambda dm: self.audio_features_loaded_label_text(dm),
                )  # audio features info label
                ui.button(
                    "Download Audio Features",
                    on_click=lambda: ui.download(
                        self.data_manager.audio_features_as_bytes(),
                        "audio_features.json",
                        "application/json",
                    ),
                ).bind_enabled_from(
                    self, "data_manager", lambda dm: not dm.audio_features.is_empty()
                )

    def create_widget(self, *args, **kwargs) -> None:
        with ui.column() as widget:
            with ui.row():
                self.create_streaming_history_section()
                self.create_audio_features_section()
        return widget
