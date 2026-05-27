export function IngestionActions({
  importDirectory,
  importing,
  importMessage,
  reindexMessage,
  onImportDirectoryChange,
  onImportDocuments,
  onImportSourcePacks,
  onReindexSources,
}: {
  importDirectory: string;
  importing: boolean;
  importMessage: string;
  reindexMessage: string;
  onImportDirectoryChange: (value: string) => void;
  onImportDocuments: () => void;
  onImportSourcePacks: () => void;
  onReindexSources: () => void;
}) {
  return (
    <div className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
        Ingestion Actions
      </p>
      <label className="mt-4 block text-sm font-semibold text-slate-700">
        Local document directory
        <input
          className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
          value={importDirectory}
          onChange={(event) => onImportDirectoryChange(event.target.value)}
          placeholder="services/ingestion/documents"
        />
      </label>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <button
          type="button"
          onClick={onImportDocuments}
          disabled={importing}
          className="rounded-2xl bg-pine px-4 py-3 font-semibold text-white disabled:opacity-60"
        >
          {importing ? "Importing..." : "Import local docs"}
        </button>
        <button
          type="button"
          onClick={onImportSourcePacks}
          disabled={importing}
          className="rounded-2xl bg-clay px-4 py-3 font-semibold text-white disabled:opacity-60"
        >
          Import source packs
        </button>
        <button
          type="button"
          onClick={onReindexSources}
          className="rounded-2xl border border-slate-300 px-4 py-3 font-semibold text-slate-700"
        >
          Reindex sources
        </button>
      </div>
      {importMessage && <p className="mt-4 text-sm text-slate-700">{importMessage}</p>}
      {reindexMessage && <p className="mt-2 text-sm text-slate-700">{reindexMessage}</p>}
    </div>
  );
}
