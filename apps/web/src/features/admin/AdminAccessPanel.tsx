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
    <div className="sheet p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="sheet-title">Admin access</h2>
        <span className={`tag ${adminAccessKey ? "tag-ok" : "tag-neutral"}`}>
          {adminAccessKey ? "Key saved" : "No key"}
        </span>
      </div>
      <p className="mt-2 text-sm leading-6 text-ink-soft">
        Source status and catalog load with beta access. Save the separate admin key here
        before editing sources, importing documents, or reindexing.
      </p>
      <label className="field-label mt-4">
        Source admin key
        <input
          className="field font-mono"
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
      <div className="mt-4 grid gap-2.5 sm:grid-cols-2">
        <button type="button" onClick={onSaveAdminKey} className="btn-primary">
          Save admin key
        </button>
        <button type="button" onClick={onClearAdminKey} className="btn-outline">
          Clear key
        </button>
      </div>
      {adminAccessMessage && (
        <p className="mt-3 text-sm text-ink-soft">{adminAccessMessage}</p>
      )}
    </div>
  );
}
