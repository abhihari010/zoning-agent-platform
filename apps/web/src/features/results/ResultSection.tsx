import type { AnalyzeResponse, AuditEvent } from "@zoning-agent/shared-schema";
import { EvidencePanel, TrustIndicatorBar, UnsupportedJurisdiction } from "../../components/ResultTrust";
import type { FeedbackState, ResultView } from "../../types/app";
import {
  confidenceLabel,
  confidenceTone,
  decisionLabel,
  decisionTone,
  evidenceLabel,
  evidenceTone,
} from "../../utils/resultLabels";

const RESULT_VIEWS: Array<{ key: ResultView; label: string }> = [
  { key: "checklist", label: "Checklist" },
  { key: "evidence", label: "Evidence" },
  { key: "trace", label: "Trace" },
];

export function ResultSection({
  result,
  resultView,
  trace,
  traceLoading,
  feedbackNote,
  feedbackState,
  feedbackMessage,
  showHumanFallback,
  onResultViewChange,
  onFeedbackNoteChange,
  onSubmitFeedback,
  onDownloadChecklist,
}: {
  result: AnalyzeResponse;
  resultView: ResultView;
  trace: AuditEvent[];
  traceLoading: boolean;
  feedbackNote: string;
  feedbackState: FeedbackState;
  feedbackMessage: string;
  showHumanFallback: boolean;
  onResultViewChange: (view: ResultView) => void;
  onFeedbackNoteChange: (value: string) => void;
  onSubmitFeedback: (helpful: boolean) => void;
  onDownloadChecklist: () => void;
}) {
  return (
    <>
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_260px]">
        <DecisionSummary result={result} showHumanFallback={showHumanFallback} />
        <EvidenceSnapshot result={result} onDownloadChecklist={onDownloadChecklist} />
      </div>

      <TrustIndicatorBar result={result} />
      <UnsupportedJurisdiction result={result} />

      <SupportingDetailsTabs
        result={result}
        resultView={resultView}
        trace={trace}
        traceLoading={traceLoading}
        onResultViewChange={onResultViewChange}
      />

      <WorkflowFeedbackPanel
        result={result}
        feedbackNote={feedbackNote}
        feedbackState={feedbackState}
        feedbackMessage={feedbackMessage}
        onFeedbackNoteChange={onFeedbackNoteChange}
        onSubmitFeedback={onSubmitFeedback}
      />
    </>
  );
}

function DecisionSummary({
  result,
  showHumanFallback,
}: {
  result: AnalyzeResponse;
  showHumanFallback: boolean;
}) {
  return (
    <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
            Decision Center
          </p>
          <h2 className="mt-2 font-heading text-3xl text-pine">
            {decisionLabel(result.feasibility.decision)}
          </h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-700">
            {result.feasibility.summary}
          </p>
        </div>
        <div
          className={`rounded-3xl border px-4 py-3 text-center ${decisionTone(
            result.feasibility.decision,
          )}`}
        >
          <p className="text-xs font-semibold uppercase tracking-[0.18em]">Confidence</p>
          <p className="mt-1 font-heading text-3xl">
            {(result.feasibility.confidence * 100).toFixed(0)}%
          </p>
        </div>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Status</p>
          <p className="mt-2 font-semibold text-slate-900">
            {result.status.replace("_", " ")}
          </p>
        </div>
        <div
          className={`rounded-2xl border p-4 ${confidenceTone(
            result.feasibility.confidence,
            result.citations.length,
          )}`}
        >
          <p className="text-xs uppercase tracking-[0.18em] opacity-75">Reliability</p>
          <p className="mt-2 font-semibold">
            {confidenceLabel(result.feasibility.confidence)}
          </p>
        </div>
        <div className={`rounded-2xl border p-4 ${evidenceTone(result.citations.length)}`}>
          <p className="text-xs uppercase tracking-[0.18em] opacity-75">Evidence</p>
          <p className="mt-2 font-semibold">{evidenceLabel(result.citations.length)}</p>
        </div>
        <div
          className={`rounded-2xl border p-4 ${
            result.warnings.length > 0
              ? "border-amber-200 bg-amber-50 text-amber-900"
              : "border-slate-200 bg-slate-50 text-slate-900"
          }`}
        >
          <p className="text-xs uppercase tracking-[0.18em] opacity-75">Warnings</p>
          <p className="mt-2 font-semibold">
            {result.warnings.length === 0
              ? "None"
              : `${result.warnings.length} signal${result.warnings.length === 1 ? "" : "s"}`}
          </p>
        </div>
      </div>

      {result.warnings.length > 0 && (
        <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-800">
            Review before relying
          </p>
          <ul className="mt-3 space-y-2 leading-6">
            {result.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      {showHumanFallback && (
        <div className="mt-5 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
          This review needs a human-in-the-loop follow-up. Please confirm the parcel
          directly with the zoning or planning office before making project or spending
          decisions.
        </div>
      )}
    </section>
  );
}

function EvidenceSnapshot({
  result,
  onDownloadChecklist,
}: {
  result: AnalyzeResponse;
  onDownloadChecklist: () => void;
}) {
  return (
    <section className="rounded-[28px] border border-pine/10 bg-slate-50/80 p-6 shadow-card">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
        Evidence Snapshot
      </p>
      <p className="mt-3 text-sm leading-6 text-slate-700">
        The answer is only as strong as the source coverage returned for this district and use.
      </p>
      <div className={`mt-5 rounded-2xl border p-4 ${evidenceTone(result.citations.length)}`}>
        <p className="text-xs uppercase tracking-[0.18em] opacity-75">Source coverage</p>
        <p className="mt-2 text-lg font-semibold">{evidenceLabel(result.citations.length)}</p>
        <p className="mt-2 text-sm leading-6">
          {result.citations.length === 0
            ? "No ordinance excerpts were retrieved, so the result should be treated as a planning-office handoff."
            : "Each cited source is available in the Evidence tab for review."}
        </p>
      </div>
      {result.citationValidation && (
        <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
            Citation validation
          </p>
          <p className="mt-2 text-sm font-semibold text-slate-900">
            {(result.citationValidation.citationCoverage * 100).toFixed(0)}% coverage
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {result.citationValidation.valid
              ? "All returned citations passed the current validation checks."
              : "Unsupported or invalid citation references were found."}
          </p>
          {result.citationValidation.unsupportedClaims.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs leading-5 text-amber-900">
              {result.citationValidation.unsupportedClaims.map((claim) => (
                <li key={claim}>{claim}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {result.pipeline && (
        <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Pipeline</p>
          <p className="mt-2 text-sm font-semibold text-slate-900">
            {result.pipeline.provider} / {result.pipeline.ragProvider}
          </p>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            {result.pipeline.version} | {result.pipeline.traceId}
          </p>
        </div>
      )}
      {result.citations.length > 0 && (
        <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
            Primary citation
          </p>
          <p className="mt-2 text-sm font-semibold text-slate-900">
            {result.citations[0].title}
          </p>
          <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-500">
            {result.citations[0].sectionRef}
          </p>
        </div>
      )}
      <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
        <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Permit path</p>
        <p className="mt-2 text-sm font-semibold text-slate-900">
          {result.checklist.steps.length} step{result.checklist.steps.length === 1 ? "" : "s"}
        </p>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          {result.checklist.permits.length > 0
            ? result.checklist.permits.join(", ")
            : "No explicit permit names were returned."}
        </p>
      </div>
      <button
        type="button"
        onClick={onDownloadChecklist}
        className="mt-5 w-full rounded-2xl bg-pine px-4 py-3 font-semibold text-white"
      >
        Download checklist
      </button>
    </section>
  );
}

function SupportingDetailsTabs({
  result,
  resultView,
  trace,
  traceLoading,
  onResultViewChange,
}: {
  result: AnalyzeResponse;
  resultView: ResultView;
  trace: AuditEvent[];
  traceLoading: boolean;
  onResultViewChange: (view: ResultView) => void;
}) {
  return (
    <div
      className={`grid gap-5 ${
        resultView === "checklist" ? "" : "lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]"
      }`}
    >
      <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
              Supporting Detail
            </p>
            <h3 className="mt-2 font-heading text-2xl text-pine">
              {resultView === "checklist"
                ? "Checklist"
                : resultView === "evidence"
                  ? "Source References"
                  : "Audit Trace"}
            </h3>
          </div>
          <div className="inline-flex w-full max-w-full overflow-x-auto rounded-2xl border border-slate-200 bg-slate-50 p-1 lg:w-auto">
            {RESULT_VIEWS.map((view) => (
              <button
                key={view.key}
                type="button"
                onClick={() => onResultViewChange(view.key)}
                className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${
                  resultView === view.key
                    ? "bg-pine text-white shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {view.label}
              </button>
            ))}
          </div>
        </div>

        {resultView === "checklist" ? (
          <ChecklistView result={result} />
        ) : resultView === "evidence" ? (
          <div className="mt-6">
            <EvidencePanel citations={result.citations} />
          </div>
        ) : (
          <TraceView trace={trace} traceLoading={traceLoading} />
        )}
      </section>
    </div>
  );
}

function ChecklistView({ result }: { result: AnalyzeResponse }) {
  return (
    <ol className="mt-6 space-y-4">
      {result.checklist.steps.map((step) => (
        <li
          key={step.order}
          className="rounded-[24px] border border-slate-200 bg-slate-50 p-5"
        >
          <div className="flex items-start gap-4">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-pine text-sm font-bold text-white">
              {step.order}
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-lg font-semibold text-slate-900">{step.action}</p>
                <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-500">
                  {step.department}
                </span>
              </div>
              <p className="mt-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                Required documents
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                {step.requiredDocs.join(", ")}
              </p>
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function TraceView({
  trace,
  traceLoading,
}: {
  trace: AuditEvent[];
  traceLoading: boolean;
}) {
  return (
    <div className="mt-6 grid gap-3">
      {traceLoading ? (
        <p className="text-sm text-slate-600">Loading trace...</p>
      ) : trace.length > 0 ? (
        trace.map((event) => (
          <div
            key={`${event.stage}-${event.createdAt}`}
            className="rounded-2xl border border-slate-200 bg-slate-50 p-4"
          >
            <p className="font-semibold text-slate-900">
              {event.stage.replaceAll(".", " / ")}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              {new Date(event.createdAt).toLocaleString()}
            </p>
            {Object.keys(event.details).length > 0 && (
              <pre className="mt-3 overflow-auto rounded-xl bg-white p-3 text-xs leading-5 text-slate-600">
                {JSON.stringify(event.details, null, 2)}
              </pre>
            )}
          </div>
        ))
      ) : (
        <p className="text-sm text-slate-600">Trace events will appear here after a run.</p>
      )}
    </div>
  );
}

function WorkflowFeedbackPanel({
  result,
  feedbackNote,
  feedbackState,
  feedbackMessage,
  onFeedbackNoteChange,
  onSubmitFeedback,
}: {
  result: AnalyzeResponse;
  feedbackNote: string;
  feedbackState: FeedbackState;
  feedbackMessage: string;
  onFeedbackNoteChange: (value: string) => void;
  onSubmitFeedback: (helpful: boolean) => void;
}) {
  return (
    <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_220px]">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
            Workflow Feedback
          </p>
          <p className="mt-3 text-sm leading-6 text-slate-700">
            Tell us whether this result felt clear enough to act on, and where the
            structure or explanation still needs work.
          </p>
          <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-800">
              Legal reminder
            </p>
            <ul className="mt-3 space-y-3 text-sm leading-6 text-amber-950">
              {result.disclaimers.map((disclaimer) => (
                <li key={disclaimer}>{disclaimer}</li>
              ))}
            </ul>
          </div>
          <textarea
            className="mt-4 min-h-[120px] w-full rounded-2xl border border-slate-300 bg-slate-50/60 px-4 py-3 text-sm outline-none transition focus:border-clay focus:ring-2 focus:ring-clay"
            value={feedbackNote}
            onChange={(event) => onFeedbackNoteChange(event.target.value)}
            placeholder="What was clear, missing, or confusing?"
          />
        </div>

        <div className="flex flex-col justify-between gap-4">
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-700">
            Use this note box for missing citations, unclear checklist steps, or anything
            that made the answer harder to trust.
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => onSubmitFeedback(true)}
              disabled={feedbackState === "submitting"}
              className="rounded-2xl bg-pine px-4 py-3 font-semibold text-white disabled:opacity-60"
            >
              Helpful
            </button>
            <button
              type="button"
              onClick={() => onSubmitFeedback(false)}
              disabled={feedbackState === "submitting"}
              className="rounded-2xl border border-slate-300 px-4 py-3 font-semibold text-slate-700 disabled:opacity-60"
            >
              Needs work
            </button>
          </div>
          {feedbackMessage && <p className="text-sm text-slate-700">{feedbackMessage}</p>}
        </div>
      </div>
    </section>
  );
}
