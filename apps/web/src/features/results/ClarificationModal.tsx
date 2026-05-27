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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
          Clarification Needed
        </p>
        <h2 className="mt-2 font-heading text-2xl text-pine">
          We need a bit more detail before finishing the zoning call.
        </h2>
        <div className="mt-5 space-y-4">
          {questions.map((question) => (
            <label key={question.id} className="block text-sm font-semibold text-slate-700">
              {question.question}
              <textarea
                className="mt-2 min-h-[96px] w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-clay focus:ring-2 focus:ring-clay"
                value={answers[question.question] ?? ""}
                onChange={(event) => onAnswerChange(question.question, event.target.value)}
              />
              <span className="mt-2 block text-xs font-normal leading-5 text-slate-500">
                {question.reason}
              </span>
            </label>
          ))}
        </div>
        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          <button
            type="button"
            onClick={onSubmit}
            disabled={submitting}
            className="flex-1 rounded-2xl bg-pine px-4 py-3 font-semibold text-white disabled:opacity-60"
          >
            {submitting ? "Submitting..." : "Continue review"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-2xl border border-slate-300 px-4 py-3 font-semibold text-slate-700"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
