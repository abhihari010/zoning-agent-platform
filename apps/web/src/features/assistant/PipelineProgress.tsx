import type { PipelineStageReport } from "@zoning-agent/shared-schema";
import type { Phase } from "../../types/app";

type StageDisplay = "pending" | "working" | "completed" | "warning" | "failed";

function displayStatus(
  phase: Phase,
  reported: string,
  index: number,
  activeStageIndex: number,
): StageDisplay {
  if (phase === "analyzing") {
    if (index < activeStageIndex) {
      return "completed";
    }
    if (index === activeStageIndex) {
      return "working";
    }
    return "pending";
  }
  if (phase === "done") {
    if (reported === "completed") {
      return "completed";
    }
    if (reported === "warning" || reported === "needs_clarification") {
      return "warning";
    }
    if (reported === "failed") {
      return "failed";
    }
    return "pending";
  }
  return "pending";
}

function stageTag(status: StageDisplay): string {
  switch (status) {
    case "working":
      return "tag-neutral border-spruce/40 text-spruce-bright";
    case "completed":
      return "tag-ok";
    case "warning":
      return "tag-hold";
    case "failed":
      return "tag-stop";
    default:
      return "tag-neutral";
  }
}

export function PipelineProgress({
  phase,
  activeStageIndex,
  stages,
}: {
  phase: Phase;
  activeStageIndex: number;
  stages: PipelineStageReport[];
}) {
  return (
    <div className="sheet p-6 md:p-8">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="sheet-title">Review pipeline</h2>
        <p className="font-mono text-[11px] uppercase tracking-wide text-ink-faint">
          {phase === "analyzing"
            ? "Running"
            : phase === "intake"
              ? "Validating address"
              : "Latest result"}
        </p>
      </div>

      <ol className="mt-5">
        {stages.map((stage, index) => {
          const status = displayStatus(phase, stage.status, index, activeStageIndex);
          const isActive = status === "working";
          const isLast = index === stages.length - 1;
          return (
            <li key={stage.key} className="relative flex gap-4 pb-5 last:pb-0">
              {!isLast && (
                <span
                  aria-hidden="true"
                  className="absolute left-[13px] top-7 h-[calc(100%-1.75rem)] w-px bg-rule"
                />
              )}
              <span
                className={`relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-sm border font-mono text-[11px] font-semibold transition-colors duration-med ease-out ${
                  isActive
                    ? "survey-pulse border-spruce bg-spruce text-white"
                    : status === "completed"
                      ? "border-spruce/40 bg-spruce-wash text-spruce-bright"
                      : "border-rule bg-well text-ink-faint"
                }`}
              >
                {String(index + 1).padStart(2, "0")}
              </span>
              <div className="min-w-0 flex-1 pt-0.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-ink">{stage.label}</p>
                  <span className={`tag ${stageTag(status)}`}>
                    {status === "working" ? "Working" : status.replace("_", " ")}
                  </span>
                </div>
                <p className="mt-0.5 text-sm leading-6 text-ink-soft">{stage.headline}</p>
                {stage.details.length > 0 && (
                  <ul className="mt-1.5 space-y-1 text-[13px] leading-5 text-ink-faint">
                    {stage.details.map((detail) => (
                      <li key={detail}>{detail}</li>
                    ))}
                  </ul>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
