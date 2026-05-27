import type { AnalyzeResponse } from "@zoning-agent/shared-schema";
import { authMode, type IntakeResponse, type JurisdictionCoverage } from "../../api";
import {
  coverageLabel,
  decisionLabel,
  supportStatusLabel,
  supportStatusTone,
} from "../../utils/resultLabels";

export function CaseSnapshot({
  intake,
  result,
  currentCoverage,
  deletingProjectId,
  onDownloadChecklist,
  onDeleteCurrentProject,
}: {
  intake: IntakeResponse | null;
  result: AnalyzeResponse | null;
  currentCoverage?: JurisdictionCoverage;
  deletingProjectId: string | null;
  onDownloadChecklist: () => void;
  onDeleteCurrentProject: () => void;
}) {
  return (
    <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
        Case Snapshot
      </p>
      {intake ? (
        <div className="mt-4 space-y-3 text-sm text-slate-700">
          {result && (
            <div className="grid gap-2">
              <button
                type="button"
                onClick={onDownloadChecklist}
                className="w-full rounded-2xl bg-pine px-4 py-3 text-sm font-semibold text-white"
              >
                Download checklist
              </button>
              {authMode === "supabase" && (
                <button
                  type="button"
                  onClick={onDeleteCurrentProject}
                  disabled={deletingProjectId === intake.projectId}
                  className="w-full rounded-2xl border border-red-200 px-4 py-3 text-sm font-semibold text-red-700 disabled:opacity-60"
                >
                  {deletingProjectId === intake.projectId ? "Deleting project" : "Delete saved project"}
                </button>
              )}
            </div>
          )}
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
              Normalized address
            </p>
            <p className="mt-2 font-semibold text-slate-900">{intake.normalizedAddress}</p>
          </div>
          <div className={`rounded-2xl border p-4 ${supportStatusTone(intake.supportStatus)}`}>
            <p className="text-xs uppercase tracking-[0.18em] opacity-75">Jurisdiction</p>
            <p className="mt-2 font-semibold">
              {intake.jurisdictionName ?? intake.jurisdictionId ?? "Unknown jurisdiction"}
            </p>
            <p className="mt-1 text-xs font-semibold uppercase tracking-[0.14em] opacity-80">
              {coverageLabel(intake.coverageStatus ?? currentCoverage?.coverageStatus)}
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
              Coverage Trust
            </p>
            <p className="mt-2 text-sm font-semibold text-slate-900">
              {supportStatusLabel(intake.supportStatus)}
            </p>
            <p className="mt-2 text-xs leading-5 text-slate-600">
              Last verified: {currentCoverage?.lastVerifiedAt ?? "Not recorded"}
            </p>
            {(intake.planningContact?.url || currentCoverage?.planningContact.url) && (
              <a
                className="mt-3 inline-flex text-sm font-semibold text-clay underline-offset-2 hover:underline"
                href={intake.planningContact?.url ?? currentCoverage?.planningContact.url}
                target="_blank"
                rel="noreferrer"
              >
                Planning office
              </a>
            )}
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">District</p>
              <p className="mt-2 font-semibold text-slate-900">
                {intake.district.replace(/-/g, " ")}
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Coordinates</p>
              <p className="mt-2 font-semibold text-slate-900">
                {intake.latitude != null && intake.longitude != null
                  ? `${intake.latitude.toFixed(4)}, ${intake.longitude.toFixed(4)}`
                  : "Unavailable"}
              </p>
            </div>
          </div>
          {result && (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Decision</p>
              <div className="mt-2 flex items-center justify-between gap-3">
                <p className="font-semibold text-slate-900">
                  {decisionLabel(result.feasibility.decision)}
                </p>
                <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-600">
                  {(result.feasibility.confidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          )}
        </div>
      ) : (
        <p className="mt-4 text-sm leading-6 text-slate-600">
          Normalized parcel context appears here after intake succeeds.
        </p>
      )}
    </section>
  );
}
