import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { AnalyzeResponse } from "@zoning-agent/shared-schema";
import {
  authMode,
  deleteProject,
  fetchProjectResult,
  type IntakeResponse,
  type JurisdictionCoverage,
  type ProjectSummary,
} from "../../api";
import type { ResultView } from "../../types/app";
import {
  buildChecklistDownload,
  downloadTextFile,
} from "../../utils/downloads";
import { coverageLabel } from "../../utils/resultLabels";
import { useFeedback } from "../../hooks/useFeedback";
import { useTrace } from "../../hooks/useTrace";
import { ResultSection } from "./ResultSection";

// Read-only record of a saved review. Reached at /reviews/:projectId — either
// seeded with the result of a run that just finished (via location.state) or
// refetched from the API for deep links and the saved-reviews list.
export function ReviewRecordPage({
  projectId,
  projects,
  projectsLoading,
  coverage,
  isAdmin,
  onDeleted,
}: {
  projectId: string;
  projects: ProjectSummary[];
  projectsLoading: boolean;
  coverage: JurisdictionCoverage[];
  isAdmin: boolean;
  onDeleted: () => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const seededResult =
    (location.state as { result?: AnalyzeResponse } | null)?.result ?? null;
  const [result, setResult] = useState<AnalyzeResponse | null>(seededResult);
  const [loading, setLoading] = useState(!seededResult);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [resultView, setResultView] = useState<ResultView>("checklist");

  const summary =
    projects.find((project) => project.projectId === projectId) ?? null;
  const jurisdictionCoverage = coverage.find(
    (item) => item.jurisdictionId === summary?.jurisdictionId,
  );

  // Minimal intake shape so the trace/feedback hooks and checklist download
  // stay keyed to this saved project without a live intake round trip.
  const recordIntake = useMemo<IntakeResponse | null>(
    () =>
      summary
        ? {
            projectId: summary.projectId,
            normalizedAddress: summary.normalizedAddress,
            district: summary.district,
            status: "created",
            supportStatus: "supported",
            jurisdictionId: summary.jurisdictionId,
            jurisdictionName: summary.jurisdictionName,
            followUpQuestions: [],
          }
        : null,
    [summary],
  );

  const { trace, traceLoading } = useTrace({
    intake: recordIntake,
    result,
    phase: "done",
    isAdmin,
  });
  const {
    feedbackNote,
    setFeedbackNote,
    feedbackState,
    feedbackMessage,
    onSubmitFeedback,
  } = useFeedback(recordIntake);

  useEffect(() => {
    if (seededResult) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setResult(null);
    setResultView("checklist");
    fetchProjectResult(projectId)
      .then((savedResult) => {
        if (!cancelled) {
          setResult(savedResult);
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Failed to load this review.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  function downloadChecklist() {
    if (!result) {
      return;
    }
    downloadTextFile(
      "zoning-checklist.txt",
      buildChecklistDownload(
        recordIntake,
        result,
        summary?.projectDescription ?? "",
      ),
    );
  }

  async function onDelete() {
    const confirmed = window.confirm(
      "Delete this saved zoning review? This cannot be undone.",
    );
    if (!confirmed) {
      return;
    }
    try {
      setDeleting(true);
      await deleteProject(projectId);
      onDeleted();
    } catch (deleteError) {
      setError(
        deleteError instanceof Error
          ? deleteError.message
          : "Failed to delete this review.",
      );
    } finally {
      setDeleting(false);
    }
  }

  if (error) {
    return (
      <section className="enter enter-1 mx-auto max-w-[760px]">
        <div className="sheet p-6">
          <p className="text-sm leading-6 text-ink-soft">{error}</p>
          <button
            type="button"
            onClick={() => navigate("/reviews")}
            className="btn-quiet mt-4 px-3 py-1.5 text-sm"
          >
            Back to saved reviews
          </button>
        </div>
      </section>
    );
  }

  if (!summary || !result) {
    if (!projectsLoading && !loading && !summary) {
      return (
        <section className="enter enter-1 mx-auto max-w-[760px]">
          <div className="sheet p-6">
            <p className="text-sm leading-6 text-ink-soft">
              This review was not found. It may have been deleted.
            </p>
            <button
              type="button"
              onClick={() => navigate("/reviews")}
              className="btn-quiet mt-4 px-3 py-1.5 text-sm"
            >
              Back to saved reviews
            </button>
          </div>
        </section>
      );
    }
    return (
      <section className="enter enter-1 mx-auto max-w-[760px]">
        <p className="px-1 py-6 text-sm text-ink-soft">Loading review…</p>
      </section>
    );
  }

  const showHumanFallback =
    result.status === "low_confidence" ||
    result.feasibility.decision === "unknown";

  return (
    <div className="enter enter-1 mx-auto max-w-[860px] space-y-6">
      <header className="sheet p-6 md:p-8">
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4">
          <div className="min-w-0">
            <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-faint">
              Saved review ·{" "}
              {new Date(summary.updatedAt).toLocaleDateString()}
            </p>
            <h1 className="mt-2 font-mono text-lg font-semibold tracking-tight text-ink">
              {summary.normalizedAddress}
            </h1>
            {summary.projectDescription && (
              <p className="mt-2 max-w-[560px] text-sm leading-6 text-ink-soft">
                {summary.projectDescription}
              </p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-ink-soft">
              <span className="font-medium text-ink">
                {summary.jurisdictionName ??
                  summary.jurisdictionId ??
                  "Unknown jurisdiction"}
              </span>
              <span className="font-mono text-[13px] uppercase">
                {summary.district.replace(/-/g, " ")}
              </span>
              <span className="tag tag-neutral">
                {coverageLabel(jurisdictionCoverage?.coverageStatus)}
              </span>
              {jurisdictionCoverage?.planningContact.url && (
                <a
                  className="text-[13px] font-medium text-spruce-bright underline-offset-2 hover:underline"
                  href={jurisdictionCoverage.planningContact.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Planning office
                </a>
              )}
            </div>
          </div>
          <div className="flex shrink-0 flex-col gap-2">
            <button
              type="button"
              onClick={() =>
                navigate(
                  `/review?address=${encodeURIComponent(summary.normalizedAddress)}`,
                )
              }
              className="btn-outline px-3 py-1.5 text-sm"
            >
              Run a new review here
            </button>
            {authMode === "supabase" && (
              <button
                type="button"
                onClick={() => {
                  void onDelete();
                }}
                disabled={deleting}
                className="btn-danger px-3 py-1.5 text-sm"
              >
                {deleting ? "Deleting review…" : "Delete review"}
              </button>
            )}
          </div>
        </div>
      </header>

      <ResultSection
        result={result}
        resultView={resultView}
        trace={trace}
        traceLoading={traceLoading}
        feedbackNote={feedbackNote}
        feedbackState={feedbackState}
        feedbackMessage={feedbackMessage}
        showHumanFallback={showHumanFallback}
        showTrace={isAdmin}
        showFeedback={Boolean(seededResult)}
        onResultViewChange={setResultView}
        onFeedbackNoteChange={setFeedbackNote}
        onSubmitFeedback={(helpful) => {
          void onSubmitFeedback(helpful);
        }}
        onDownloadChecklist={downloadChecklist}
      />
    </div>
  );
}
