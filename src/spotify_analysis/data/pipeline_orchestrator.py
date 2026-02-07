import asyncio

from .data_pipeline.pipelines import DataPipeline

class PipelineOrchestrator:
    pipelines: dict[DataPipeline, asyncio.Queue]
    
    def __init__(self) -> None:
        self.pipelines = {}
    
    def register_pipeline(self, data_pipeline: DataPipeline, input_queue: asyncio.Queue) -> None:
        self.pipelines[data_pipeline] = input_queue
        
    async def dispatch_pipelines(self) -> None:
        async with asyncio.TaskGroup() as tg:
            for pipeline, input_queue in self.pipelines.items():
                tg.create_task(pipeline.run(input_queue))