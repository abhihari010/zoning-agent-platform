import type { FollowUpQuestion } from "@zoning-agent/shared-schema";

export function ClarificationModal({
  questions,
  answers,
  submitting,
  onAnswerChange,
  onSubmit,
  onClose,
}: {
  questions: FollowUpQuestion[];
  answers: Record<string, string>;
  submitting: boolean;
  onAnswerChange: (question: string, value: string) => void;
  onSubmit: () => void;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4 backdrop-blur-sm">
      <div className="sheet rise max-h-[90dvh] w-full max-w-2xl overflow-auto shadow-raised">
        <div className="border-b border-rule bg-well/70 px-6 py-2.5 md:px-8">
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-faint">
            Clarification needed
          </p>
        </div>
        <div className="p-6 md:p-8">
          <h2 className="text-xl font-bold tracking-tight text-ink">
            A few details before the determination can be finished
          </h2>
          <div className="mt-5 space-y-4">
            {questions.map((question) => (
              <label key={question.id} className="field-label">
                {question.question}
                <textarea
                  className="field min-h-[90px]"
                  value={answers[question.question] ?? ""}
                  onChange={(event) => onAnswerChange(question.question, event.target.value)}
                />
                <span className="mt-1.5 block text-xs font-normal leading-5 text-ink-faint">
                  {question.reason}
                </span>
              </label>
            ))}
          </div>
          <div className="mt-6 flex flex-col gap-2.5 sm:flex-row">
            <button
              type="button"
              onClick={onSubmit}
              disabled={submitting}
              className="btn-primary flex-1"
            >
              {submitting ? "Submitting…" : "Continue review"}
            </button>
            <button type="button" onClick={onClose} className="btn-outline">
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
