import type { ReactNode } from "react";
import type { AnalyzeResponse } from "@zoning-agent/shared-schema";
import { authMode, type IntakeResponse, type JurisdictionCoverage } from "../../api";
import {
  coverageLabel,
  decisionLabel,
  supportStatusLabel,
  supportStatusTone,
} from "../../utils/resultLabels";

function CaseRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="py-3 first:pt-0 last:pb-0">
      <p className="text-xs font-medium text-ink-faint">{label}</p>
      {children}
    </div>
  );
}

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
    <section className="sheet p-5">
      <h2 className="text-sm font-bold text-ink">Case snapshot</h2>
      {intake ? (
        <div className="mt-3">
          <div className="divide-y divide-rule">
            <CaseRow label="Address">
              <p className="mt-1 font-mono text-[13px] font-medium leading-5 text-ink">
                {intake.normalizedAddress}
              </p>
            </CaseRow>
            <CaseRow label="Jurisdiction">
              <p className="mt-1 text-sm font-medium text-ink">
                {intake.jurisdictionName ?? intake.jurisdictionId ?? "Unknown jurisdiction"}
              </p>
              <span
                className={`mt-1.5 inline-flex rounded-sm border px-2 py-0.5 font-mono text-[11px] font-medium uppercase tracking-wide ${supportStatusTone(intake.supportStatus)}`}
              >
                {coverageLabel(intake.coverageStatus ?? currentCoverage?.coverageStatus)}
              </span>
            </CaseRow>
            <CaseRow label="Coverage trust">
              <p className="mt-1 text-sm font-medium text-ink">
                {supportStatusLabel(intake.supportStatus)}
              </p>
              <p className="mt-1 text-xs leading-5 text-ink-soft">
                Last verified: {currentCoverage?.lastVerifiedAt ?? "not recorded"}
              </p>
              {(intake.planningContact?.url || currentCoverage?.planningContact.url) && (
                <a
                  className="mt-1.5 inline-flex text-[13px] font-medium text-spruce-bright underline-offset-2 hover:underline"
                  href={intake.planningContact?.url ?? currentCoverage?.planningContact.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Planning office
                </a>
              )}
            </CaseRow>
            <CaseRow label="District">
              <p className="mt-1 font-mono text-[13px] font-medium uppercase text-ink">
                {intake.district.replace(/-/g, " ")}
              </p>
            </CaseRow>
            <CaseRow label="Coordinates">
              <p className="tabular mt-1 font-mono text-[13px] text-ink-soft">
                {intake.latitude != null && intake.longitude != null
                  ? `${intake.latitude.toFixed(4)}, ${intake.longitude.toFixed(4)}`
                  : "Unavailable"}
              </p>
            </CaseRow>
            {result && (
              <CaseRow label="Determination">
                <div className="mt-1 flex items-center justify-between gap-3">
                  <p className="text-sm font-medium text-ink">
                    {decisionLabel(result.feasibility.decision)}
                  </p>
                  <span className="tabular font-mono text-xs text-ink-faint">
                    {(result.feasibility.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </CaseRow>
            )}
          </div>
          {result && (
            <div className="mt-4 grid gap-2 border-t border-rule pt-4">
              <button type="button" onClick={onDownloadChecklist} className="btn-primary w-full">
                Download checklist
              </button>
              {authMode === "supabase" && (
                <button
                  type="button"
                  onClick={onDeleteCurrentProject}
                  disabled={deletingProjectId === intake.projectId}
                  className="btn-danger w-full"
                >
                  {deletingProjectId === intake.projectId
                    ? "Deleting project…"
                    : "Delete saved project"}
                </button>
              )}
            </div>
          )}
        </div>
      ) : (
        <p className="mt-3 text-sm leading-6 text-ink-soft">
          Normalized parcel context appears here after intake succeeds.
        </p>
      )}
    </section>
  );
}
