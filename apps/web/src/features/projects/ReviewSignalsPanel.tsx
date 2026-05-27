export function ReviewSignalsPanel({ prompts }: { prompts: string[] }) {
  return (
    <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
        Review Signals
      </p>
      <div className="mt-4 space-y-3">
        {prompts.length > 0 ? (
          prompts.map((prompt) => (
            <div key={prompt} className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
              <p className="text-sm text-amber-900">{prompt}</p>
            </div>
          ))
        ) : (
          <p className="text-sm leading-6 text-slate-600">
            Follow-up questions and confidence warnings will appear here when the review needs more detail.
          </p>
        )}
      </div>
    </section>
  );
}
