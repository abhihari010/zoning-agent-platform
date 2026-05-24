from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal


PipelineEventStatus = Literal["started", "completed", "warning", "failed", "skipped"]

PIPELINE_EVENT_TYPES = (
    "address_normalization",
    "jurisdiction_resolution",
    "district_resolution",
    "unsupported_jurisdiction_early_exit",
)


@dataclass
class PipelineTraceRecorder:
    project_id: str | None = None
    audit: Callable[[str, str, dict | None], None] | None = None

    def record(
        self,
        stage: str,
        status: PipelineEventStatus = "completed",
        details: dict | None = None,
    ) -> None:
        if not self.project_id or not self.audit:
            return
        self.audit(f"pipeline.{stage}.{status}", self.project_id, details)
