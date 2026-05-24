__all__ = ["PipelineContext", "PipelineTraceRecorder", "ZoningOrchestrator"]


def __getattr__(name: str):
    if name == "PipelineContext":
        from app.orchestrator.pipeline_context import PipelineContext

        return PipelineContext
    if name == "PipelineTraceRecorder":
        from app.orchestrator.pipeline_events import PipelineTraceRecorder

        return PipelineTraceRecorder
    if name == "ZoningOrchestrator":
        from app.orchestrator.zoning_orchestrator import ZoningOrchestrator

        return ZoningOrchestrator
    raise AttributeError(name)
