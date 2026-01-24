from .pipelines import DataPipeline

class PipelineOrchestrator:
    pipelines: list[DataPipeline]
    
    def register_pipeline(self, data_pipeline: DataPipeline) -> None:
        self.pipelines.append(data_pipeline)
        
    async def dispatch_pipelines(self) -> None:
        for pipeline in self.pipelines:
            await pipeline.run()