export function AdminAccessPanel({
  adminAccessKey,
  adminAccessInput,
  adminAccessMessage,
  onAdminAccessInputChange,
  onSaveAdminKey,
  onClearAdminKey,
}: {
  adminAccessKey: string;
  adminAccessInput: string;
  adminAccessMessage: string;
  onAdminAccessInputChange: (value: string) => void;
  onSaveAdminKey: () => void;
  onClearAdminKey: () => void;
}) {
  return (
    <div className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
        Admin Access
      </p>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        Source status and catalog load with beta access. Save the separate admin key here
        before editing sources, importing documents, or reindexing.
      </p>
      <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Write access</p>
        <p className="mt-2 text-sm font-semibold text-slate-900">
          {adminAccessKey ? "Admin key saved for this session" : "No admin key saved"}
        </p>
      </div>
      <label className="mt-4 block text-sm font-semibold text-slate-700">
        Source admin key
        <input
          className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
          type="password"
          value={adminAccessInput}
          onChange={(event) => onAdminAccessInputChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              onSaveAdminKey();
            }
          }}
        />
      </label>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <button
          type="button"
          onClick={onSaveAdminKey}
          className="rounded-2xl bg-clay px-4 py-3 font-semibold text-white"
        >
          Save admin key
        </button>
        <button
          type="button"
          onClick={onClearAdminKey}
          className="rounded-2xl border border-slate-300 px-4 py-3 font-semibold text-slate-700"
        >
          Clear key
        </button>
      </div>
      {adminAccessMessage && (
        <p className="mt-4 text-sm text-slate-700">{adminAccessMessage}</p>
      )}
    </div>
  );
}
