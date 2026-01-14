import io
import logging
from multiprocessing import Manager
from typing import Optional

from nicegui import run, ui

from spotify_analysis.data.data_manager import DataManager
from spotify_analysis.data.services import recognise_listening_history_service, ServiceNotFoundError, service_data_pipelines

from .widget import DataWidget
from .events import EventType


logger = logging.getLogger(__name__)


class DataLoaderWidget(DataWidget):
    """
    Widget for handling data loading and management.
    """
    
    fileload_in_progress: bool = False

    async def handle_multi_upload(self, event) -> None:
        """
        Called when a multiple file upload is completed.
        Appends the newly uploaded files to the data_manager and notifies all widgets of the change.
        """
        
        logger.debug("Handling multi upload...")
        
        file_names: list[str] = event.names
        file_contents: list[io.BytesIO] = event.contents
        
        logger.debug(f"File names: {file_names}")
        
        listening_history_services = [recognise_listening_history_service(file_name) for file_name in file_names]
        for lhs in listening_history_services:
            data_pipeline = service_data_pipelines[lhs]
            await self.get_credentials(data_pipeline.enricher.credential_fields)
        
        await self.emit_event(EventType.START_FILE_LOAD)
        for i, (file_name, file_content) in enumerate(zip(file_names, file_contents)):
            logger.debug(f"Loading file {file_name}...")
            self.file_upload_progressbar.value = (i+1)/(len(file_names)+1) + 0.05
            
            listening_history_service = listening_history_services[i]
            data_pipeline = service_data_pipelines[listening_history_service]

            await self.data_manager.load_file_to_database(
                data_pipeline, file_content
            )

            await self.emit_event(event_type=EventType.DATA_ADDED)

        await self.emit_event(EventType.END_FILE_LOAD)

    async def get_credentials(self, credential_fields):
        enricher_credentials = self.data_manager.get_credentials(credential_fields)
        logger.debug(f"Enricher credentials: {enricher_credentials}")
        
        if any(not cred_value for cred_value in enricher_credentials.values()):
            credentials_dialog = self.create_credentials_dialog(enricher_credentials)
            
            cred_inputs: Optional[dict[str, ui.input]] = await credentials_dialog
            
            if cred_inputs:
                enricher_credentials = {cred: inp.value for cred, inp in cred_inputs.items()}
                self.data_manager.set_credentials(enricher_credentials)

    def create_credentials_dialog(self, current_credentials: dict[str, str]):
        logger.debug("Creating credentials dialog...")
        label_inputs: dict[str, ui.input] = {}
        with ui.dialog() as dialog, ui.card():
            for credential, current_value in current_credentials.items():
                label_inputs[credential] = ui.input(label=credential, value=current_value or "")
            with ui.row():
                ui.button("Cancel", on_click=lambda: dialog.submit(None)).tooltip("Proceed without entering credentials. Tracks will be differentiated based on spotify's track id. This may lead to duplicates in the final data set.")
                ui.button("Submit", on_click=lambda: dialog.submit(label_inputs)).tooltip("Enter credentials to differentiate tracks based on ISRC (International Standard Recording Code).")

        return dialog

    def on_event(self, event_type, *args, **kwargs):
        match event_type:
            case EventType.START_FILE_LOAD:
                self.fileload_in_progress = True
            case EventType.END_FILE_LOAD:
                self.fileload_in_progress = False
        return super().on_event(event_type, *args, **kwargs)

    def data_loaded_label_text(self) -> str:
        return (
            f"Data from {len(self.data_manager.files_loaded)} files loaded."
            if not self.data_manager.has_listening_history_data
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

    async def get_spotify_api_data_callback(
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
                # label.bind_text_from(
                #     self, "data_manager", lambda dm: self.data_loaded_label_text()
                # )
                with ui.tooltip() as tooltip:
                    tooltip.style("white-space: pre-wrap")
                    # tooltip.bind_text_from(
                    #     self,
                    #     "data_manager",
                    #     lambda dm: "\n".join(sorted(dm.files_loaded)),
                    # )
                    tooltip.bind_visibility_from(
                        self.data_manager.static_data_metadata,
                        "has_listening_history_data",
                        lambda has_data: not has_data,
                    )
            # streaming history upload
            self.file_upload_progressbar = ui.linear_progress(value=0).bind_visibility_from(self, "fileload_in_progress")
            ui.upload(
                multiple=True,
                max_files=20,
                max_file_size=20_000_000,
                on_rejected=lambda e: ui.notification(f"Upload failed: {e}", type="negative"),
                on_multi_upload=lambda event: self.handle_multi_upload(event),
            )

    def create_api_section(self):
        with ui.column():
            with ui.row():
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
                        label="Spotify API Client ID",
                        placeholder="Your Client ID",
                    )
                    client_secret = ui.input(
                        label="Spotify API Client Secret",
                        placeholder="Your Client Secret",
                    )
                    with ui.row():
                        ui.button(
                            "Get Track Audio Features",
                            on_click=lambda: self.get_spotify_api_data_callback(
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
            ui.button("Add Spotify API Data", on_click=dialog.open).bind_enabled_from(
                self.data_manager, "streaming_data", lambda x: not x.is_empty()
            )

    async def create_widget(self, *args, **kwargs) -> None:
        logger.debug("Creating widget...")
        with ui.column() as widget:
            with ui.row():
                self.create_streaming_history_section()
                self.create_api_section()
        return widget
