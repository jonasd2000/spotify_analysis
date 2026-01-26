import asyncio

from .data_pipeline.pipelines import DataPipeline

class PipelineOrchestrator:
    pipelines: dict[DataPipeline, asyncio.Queue]
    
    def __init__(self) -> None:
        self.pipelines = {}
    
    def register_pipeline[R, G, P, T](self, data_pipeline: DataPipeline[R, G, P, T], input_queue: asyncio.Queue[R]) -> None:
        self.pipelines[data_pipeline] = input_queue
        
    async def dispatch_pipelines(self) -> None:
        for pipeline, input_queue in self.pipelines.items():
            await pipeline.run(input_queue)