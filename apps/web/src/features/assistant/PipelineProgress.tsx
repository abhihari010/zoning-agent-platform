import type { PipelineStageReport } from "@zoning-agent/shared-schema";
import type { Phase } from "../../types/app";
import { statusTone } from "../../utils/resultLabels";

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
    <div className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
            Pipeline Progress
          </p>
          <h2 className="mt-2 font-heading text-2xl text-pine">Orchestrated workflow</h2>
        </div>
        <p className="text-sm text-slate-600">
          {phase === "analyzing"
            ? "Running now"
            : phase === "done"
              ? "Latest result"
              : "Waiting for input"}
        </p>
      </div>

      <div className="mt-5 grid gap-3">
        {stages.map((stage, index) => {
          const isActive = phase === "analyzing" && index === activeStageIndex;
          return (
            <article
              key={stage.key}
              className={`rounded-2xl border p-4 ${statusTone(stage.status, isActive)}`}
            >
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-semibold text-slate-900">{stage.label}</p>
                  <p className="mt-1 text-sm text-slate-700">{stage.headline}</p>
                </div>
                <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600">
                  {isActive ? "Working" : stage.status.replace("_", " ")}
                </span>
              </div>
              {stage.details.length > 0 && (
                <ul className="mt-3 space-y-1 text-sm text-slate-600">
                  {stage.details.map((detail) => (
                    <li key={detail}>{detail}</li>
                  ))}
                </ul>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
