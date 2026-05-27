export function BetaAccessGate({
  accessInput,
  error,
  onAccessInputChange,
  onUnlock,
}: {
  accessInput: string;
  error: string;
  onAccessInputChange: (value: string) => void;
  onUnlock: () => void;
}) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[linear-gradient(180deg,#f8f3ea_0%,#efe5d5_100%)] px-4 text-slate-900">
      <section className="w-full max-w-md rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
          Private Beta
        </p>
        <h1 className="mt-3 font-heading text-3xl text-pine">Zoning Review Platform</h1>
        <p className="mt-3 text-sm leading-6 text-slate-700">
          Enter your beta access key to open the zoning review workspace.
        </p>
        <label className="mt-6 block text-sm font-semibold text-slate-700">
          Access key
          <input
            className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-clay focus:ring-2 focus:ring-clay"
            type="password"
            value={accessInput}
            onChange={(event) => onAccessInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                onUnlock();
              }
            }}
          />
        </label>
        {error && (
          <p className="mt-3 rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            {error}
          </p>
        )}
        <button
          type="button"
          onClick={onUnlock}
          className="mt-5 w-full rounded-2xl bg-pine px-4 py-3 font-semibold text-white"
        >
          Unlock beta
        </button>
      </section>
    </main>
  );
}
