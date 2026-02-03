import asyncio
import io
import logging
from multiprocessing import Manager
from typing import Optional

from nicegui import run, ui

from spotify_analysis.data.data_manager import DataManager
from spotify_analysis.data.services import recognise_listening_history_service, ServiceNotFoundError#, service_data_pipelines
from spotify_analysis.data.pipeline_orchestrator import PipelineOrchestrator
from spotify_analysis.data.data_pipeline.pipeline_factory import spotify_listening_history_file_pipeline_module_factory, spotify_api_pipeline_module_factory
from spotify_analysis.data.data_pipeline.pipelines import DataPipeline

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
        
        # listening_history_services = [recognise_listening_history_service(file_name) for file_name in file_names]
        # for lhs in listening_history_services:
        #     data_pipeline = service_data_pipelines[lhs]
        #     await self.get_credentials(data_pipeline.enricher.credential_fields)
        
        file_content_queue: asyncio.Queue[io.BytesIO] = asyncio.Queue()
        uri_queue: asyncio.Queue[str] = asyncio.Queue()
        
        pipeline_orchestrator = PipelineOrchestrator()
        spotify_file_pipeline_module = spotify_listening_history_file_pipeline_module_factory(self.data_manager.async_engine)
        spotify_api_pipeline_module = spotify_api_pipeline_module_factory(self.data_manager.async_engine)
        
        pipeline = DataPipeline(main_module=spotify_file_pipeline_module)
        pipeline.add_module(on=(spotify_file_pipeline_module, 1), module=spotify_api_pipeline_module)
        
        pipeline_orchestrator.register_pipeline(pipeline, file_content_queue)
        
        pipeline_orchestrator_task = asyncio.create_task(pipeline_orchestrator.dispatch_pipelines())
        
        await self.emit_event(EventType.START_FILE_LOAD)
        for i, (file_name, file_content) in enumerate(zip(file_names, file_contents)):
            await file_content_queue.put(file_content)
            # logger.debug(f"Loading file {i}/{len(file_names)}: {file_name}...")
            # self.file_upload_progressbar.value = (i+1)/(len(file_names)+1)
            # self.file_upload_progress_label.set_text(f"Uploading File {i+1}/{len(file_names)}")
            
            # listening_history_service = listening_history_services[i]
            # data_pipeline = service_data_pipelines[listening_history_service]

            # await self.data_manager.load_file_to_database(
            #     data_pipeline, file_content
            # )

        
        file_content_queue.shutdown()
        
        await pipeline_orchestrator_task
        await self.data_manager.refresh_metadata()
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
            self.file_upload_progressbar = ui.linear_progress(value=0, show_value=False).bind_visibility_from(self, "fileload_in_progress")
            self.file_upload_progress_label = ui.label("Uploading...").bind_visibility_from(self, "fileload_in_progress").classes("text-center text-bold")
            ui.upload(
                multiple=True,
                max_files=20,
                max_file_size=20_000_000,
                on_rejected=lambda e: ui.notification(f"Upload failed: {e}", type="negative"),
                on_multi_upload=lambda event: self.handle_multi_upload(event),
            )

    def create_api_section(self):
        with ui.column():
            # audio features from file upload
            ui.button("Add Spotify API Data", on_click=lambda: ui.notify("TODO"))

    async def create_widget(self, *args, **kwargs) -> None:
        logger.debug("Creating widget...")
        with ui.column() as widget:
            with ui.row():
                self.create_streaming_history_section()
                self.create_api_section()
        return widget
