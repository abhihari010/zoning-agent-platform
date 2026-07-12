import { useState } from "react";
import { motion } from "motion/react";
import type { AnalyzeResponse, AuditEvent } from "@zoning-agent/shared-schema";
import {
  EvidencePanel,
  TrustIndicatorBar,
  UnsupportedJurisdiction,
} from "../../components/ResultTrust";
import type { FeedbackState, ResultView } from "../../types/app";
import {
  confidenceLabel,
  decisionLabel,
  decisionTone,
  evidenceLabel,
} from "../../utils/resultLabels";

const RESULT_VIEWS: Array<{ key: ResultView; label: string }> = [
  { key: "checklist", label: "Checklist" },
  { key: "evidence", label: "Evidence" },
  { key: "trace", label: "Trace" },
];

const EASE_OUT_EXPO = [0.16, 1, 0.3, 1] as const;

const arrivalVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0 },
};

const arrivalTransition = { duration: 0.45, ease: EASE_OUT_EXPO };

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
    <motion.div
      initial="hidden"
      animate="visible"
      variants={{ visible: { transition: { staggerChildren: 0.07 } } }}
      className="space-y-6"
    >
      <motion.div variants={arrivalVariants} transition={arrivalTransition}>
        <DecisionSummary result={result} showHumanFallback={showHumanFallback} />
      </motion.div>

      {result.trustIndicators?.jurisdictionSupported === false && (
        <motion.div variants={arrivalVariants} transition={arrivalTransition}>
          <UnsupportedJurisdiction result={result} />
        </motion.div>
      )}

      <motion.div variants={arrivalVariants} transition={arrivalTransition}>
        <SupportingDetailsTabs
          result={result}
          resultView={resultView}
          trace={trace}
          traceLoading={traceLoading}
          onResultViewChange={onResultViewChange}
          onDownloadChecklist={onDownloadChecklist}
        />
      </motion.div>

      <motion.div variants={arrivalVariants} transition={arrivalTransition}>
        <WorkflowFeedbackPanel
          result={result}
          feedbackNote={feedbackNote}
          feedbackState={feedbackState}
          feedbackMessage={feedbackMessage}
          onFeedbackNoteChange={onFeedbackNoteChange}
          onSubmitFeedback={onSubmitFeedback}
        />
      </motion.div>
    </motion.div>
  );
}

function DecisionSummary({
  result,
  showHumanFallback,
}: {
  result: AnalyzeResponse;
  showHumanFallback: boolean;
}) {
  const confidencePct = Math.round(result.feasibility.confidence * 100);
  // The signature moment: the stamp lands like a physical stamp and the
  // card takes a one-frame 1px hit on impact (brief §5C).
  const [stamped, setStamped] = useState(false);

  return (
    <section className={`sheet overflow-hidden ${stamped ? "stamp-impact" : ""}`}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule bg-well/70 px-6 py-2.5 md:px-8">
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-faint">
          Determination record
        </p>
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-faint">
          {result.status.replace(/_/g, " ")}
        </p>
      </div>

      <div className="flex flex-wrap items-start gap-x-8 gap-y-5 p-6 md:p-8">
        <motion.div
          initial={{ scale: 1.2, rotate: -6, opacity: 0 }}
          animate={{ scale: 1, rotate: -2, opacity: 1 }}
          transition={{ duration: 0.35, delay: 0.25, ease: EASE_OUT_EXPO }}
          onAnimationComplete={() => setStamped(true)}
          className={`stamp ${decisionTone(result.feasibility.decision)}`}
        >
          <span className="text-[10px] tracking-[0.22em]">Determination</span>
          <span className="mt-0.5 text-2xl font-semibold tracking-tight">
            {decisionLabel(result.feasibility.decision)}
          </span>
        </motion.div>
        <p className="min-w-[220px] flex-1 pt-1 text-sm leading-7 text-ink-soft">
          {result.feasibility.summary}
        </p>
      </div>

      <dl className="grid grid-cols-1 divide-y divide-rule border-t border-rule sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <div className="px-6 py-4 md:px-8">
          <dt className="text-xs font-medium text-ink-faint">Confidence</dt>
          <dd className="mt-1 flex items-baseline gap-2">
            <span className="tabular font-mono text-2xl font-semibold text-ink">
              {confidencePct}%
            </span>
            <span className="text-xs text-ink-soft">
              {confidenceLabel(result.feasibility.confidence)}
            </span>
          </dd>
        </div>
        <div className="px-6 py-4 md:px-8">
          <dt className="text-xs font-medium text-ink-faint">Evidence</dt>
          <dd className="mt-1 flex items-baseline gap-2">
            <span className="tabular font-mono text-2xl font-semibold text-ink">
              {result.citations.length}
            </span>
            <span className="text-xs text-ink-soft">
              {evidenceLabel(result.citations.length).replace(/^\d+ /, "")}
            </span>
          </dd>
        </div>
        <div className="px-6 py-4 md:px-8">
          <dt className="text-xs font-medium text-ink-faint">Warnings</dt>
          <dd className="mt-1 flex items-baseline gap-2">
            <span className="tabular font-mono text-2xl font-semibold text-ink">
              {result.warnings.length}
            </span>
            <span className="text-xs text-ink-soft">
              {result.warnings.length === 0 ? "none raised" : "review below"}
            </span>
          </dd>
        </div>
      </dl>

      {(result.warnings.length > 0 || showHumanFallback) && (
        <div className="space-y-3 border-t border-rule p-6 md:px-8">
          {result.warnings.length > 0 && (
            <div className="rounded-sm border border-verdict-hold/30 bg-verdict-holdwash p-4 text-sm">
              <p className="font-bold text-verdict-hold">Review before relying</p>
              <ul className="mt-2 space-y-1.5 leading-6 text-ink-soft">
                {result.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
          {showHumanFallback && (
            <div className="rounded-sm border border-verdict-stop/25 bg-verdict-stopwash p-4 text-sm leading-6 text-ink-soft">
              <span className="font-bold text-verdict-stop">
                This review needs a human follow-up.
              </span>{" "}
              Confirm the parcel directly with the zoning or planning office before
              making project or spending decisions.
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function SupportingDetailsTabs({
  result,
  resultView,
  trace,
  traceLoading,
  onResultViewChange,
  onDownloadChecklist,
}: {
  result: AnalyzeResponse;
  resultView: ResultView;
  trace: AuditEvent[];
  traceLoading: boolean;
  onResultViewChange: (view: ResultView) => void;
  onDownloadChecklist: () => void;
}) {
  return (
    <section className="sheet p-6 md:p-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <h3 className="sheet-title">
          {resultView === "checklist"
            ? "Permit checklist"
            : resultView === "evidence"
              ? "Source references"
              : "Audit trace"}
        </h3>
        <div className="flex flex-wrap items-center gap-3">
          <div
            className="flex w-full max-w-full overflow-x-auto border-b border-rule md:w-auto md:border-b-0"
            role="tablist"
          >
            {RESULT_VIEWS.map((view) => {
              const isActive = resultView === view.key;
              return (
                <button
                  key={view.key}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => onResultViewChange(view.key)}
                  className={`relative px-4 py-2 text-sm font-medium transition-colors duration-fast ease-out ${
                    isActive ? "text-ink" : "text-ink-soft hover:text-ink"
                  }`}
                >
                  {view.label}
                  {isActive && (
                    <motion.span
                      layoutId="result-tab-underline"
                      className="absolute inset-x-4 bottom-0 h-0.5 bg-ink"
                      transition={{ duration: 0.25, ease: EASE_OUT_EXPO }}
                    />
                  )}
                </button>
              );
            })}
          </div>
          <button
            type="button"
            onClick={onDownloadChecklist}
            className="btn-outline px-3 py-1.5 text-sm"
          >
            Download checklist
          </button>
        </div>
      </div>

      {resultView === "checklist" ? (
        <ChecklistView result={result} />
      ) : resultView === "evidence" ? (
        <div className="mt-6 space-y-5">
          <TrustIndicatorBar result={result} />
          {result.citationValidation && (
            <CitationValidationNote validation={result.citationValidation} />
          )}
          <EvidencePanel citations={result.citations} />
        </div>
      ) : (
        <TraceView result={result} trace={trace} traceLoading={traceLoading} />
      )}
    </section>
  );
}

function CitationValidationNote({
  validation,
}: {
  validation: NonNullable<AnalyzeResponse["citationValidation"]>;
}) {
  return (
    <div className="rounded-sm border border-rule bg-well/60 p-4">
      <p className="text-xs font-medium text-ink-faint">Citation validation</p>
      <p className="tabular mt-1 font-mono text-sm font-medium text-ink">
        {(validation.citationCoverage * 100).toFixed(0)}% coverage
      </p>
      <p className="mt-1 text-xs leading-5 text-ink-soft">
        {validation.valid
          ? "All returned citations passed validation checks."
          : "Unsupported or invalid citation references were found."}
      </p>
      {validation.unsupportedClaims.length > 0 && (
        <ul className="mt-1.5 space-y-1 text-xs leading-5 text-verdict-hold">
          {validation.unsupportedClaims.map((claim) => (
            <li key={claim}>{claim}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ChecklistView({ result }: { result: AnalyzeResponse }) {
  return (
    <>
      {result.checklist.permits.length > 0 && (
        <p className="mt-6 text-sm leading-6 text-ink-soft">
          <span className="font-medium text-ink">Permits:</span>{" "}
          {result.checklist.permits.join(", ")}
        </p>
      )}
      <ol className="mt-6">
      {result.checklist.steps.map((step, index) => {
        const isLast = index === result.checklist.steps.length - 1;
        return (
          <li key={step.order} className="relative flex gap-4 pb-6 last:pb-0">
            {!isLast && (
              <span
                aria-hidden="true"
                className="absolute left-[13px] top-8 h-[calc(100%-2rem)] w-px bg-rule"
              />
            )}
            <span className="relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-sm border border-spruce/40 bg-spruce-wash font-mono text-[11px] font-semibold text-spruce-bright">
              {String(step.order).padStart(2, "0")}
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-[15px] font-medium text-ink">{step.action}</p>
                <span className="tag tag-neutral">{step.department}</span>
              </div>
              <p className="mt-1.5 text-xs font-medium text-ink-faint">
                Required documents
              </p>
              <p className="mt-0.5 text-sm leading-6 text-ink-soft">
                {step.requiredDocs.join(", ")}
              </p>
            </div>
          </li>
        );
      })}
      </ol>
    </>
  );
}

function TraceView({
  result,
  trace,
  traceLoading,
}: {
  result: AnalyzeResponse;
  trace: AuditEvent[];
  traceLoading: boolean;
}) {
  return (
    <div className="mt-6 space-y-4">
      {result.pipeline && (
        <p className="font-mono text-xs leading-5 text-ink-faint">
          {result.pipeline.provider} / {result.pipeline.ragProvider} ·{" "}
          {result.pipeline.version} · {result.pipeline.traceId}
        </p>
      )}
      {traceLoading ? (
        <p className="text-sm text-ink-soft">Loading trace…</p>
      ) : trace.length > 0 ? (
        <div className="divide-y divide-rule rounded-sm border border-rule">
          {trace.map((event) => (
            <div key={`${event.stage}-${event.createdAt}`} className="p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-mono text-[13px] font-medium text-ink">
                  {event.stage.replaceAll(".", " / ")}
                </p>
                <p className="tabular font-mono text-[11px] text-ink-faint">
                  {new Date(event.createdAt).toLocaleString()}
                </p>
              </div>
              {Object.keys(event.details).length > 0 && (
                <pre className="mt-2.5 overflow-auto rounded-sm border border-rule bg-well p-3 font-mono text-xs leading-5 text-ink-soft">
                  {JSON.stringify(event.details, null, 2)}
                </pre>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-ink-soft">Trace events will appear here after a run.</p>
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
    <section className="sheet p-6 md:p-8">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_260px]">
        <div>
          <h3 className="sheet-title">Was this result clear enough to act on?</h3>
          <p className="mt-1.5 text-sm leading-6 text-ink-soft">
            Note missing citations, unclear checklist steps, or anything that made the
            answer harder to trust.
          </p>
          <textarea
            className="field mt-4 min-h-[110px]"
            value={feedbackNote}
            onChange={(event) => onFeedbackNoteChange(event.target.value)}
            placeholder="What was clear, missing, or confusing?"
          />
          <div className="mt-3 flex flex-wrap gap-2.5">
            <button
              type="button"
              onClick={() => onSubmitFeedback(true)}
              disabled={feedbackState === "submitting"}
              className="btn-primary"
            >
              Helpful
            </button>
            <button
              type="button"
              onClick={() => onSubmitFeedback(false)}
              disabled={feedbackState === "submitting"}
              className="btn-outline"
            >
              Needs work
            </button>
          </div>
          {feedbackMessage && (
            <p className="mt-3 text-sm text-ink-soft">{feedbackMessage}</p>
          )}
        </div>

        <div className="self-start rounded-sm border border-rule bg-well/60 p-4">
          <p className="text-xs font-medium text-ink-faint">Legal reminder</p>
          <ul className="mt-2 space-y-2.5 text-xs leading-5 text-ink-soft">
            {result.disclaimers.map((disclaimer) => (
              <li key={disclaimer}>{disclaimer}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
