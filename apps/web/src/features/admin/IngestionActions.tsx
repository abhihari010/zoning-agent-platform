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
    <div className="sheet p-6">
      <h2 className="sheet-title">Ingestion</h2>
      <label className="field-label mt-4">
        Local document directory
        <input
          className="field font-mono"
          value={importDirectory}
          onChange={(event) => onImportDirectoryChange(event.target.value)}
          placeholder="services/ingestion/documents"
        />
      </label>
      <div className="mt-4 grid gap-2.5 sm:grid-cols-2">
        <button
          type="button"
          onClick={onImportDocuments}
          disabled={importing}
          className="btn-primary"
        >
          {importing ? "Importing…" : "Import local docs"}
        </button>
        <button
          type="button"
          onClick={onImportSourcePacks}
          disabled={importing}
          className="btn-outline"
        >
          Import source packs
        </button>
        <button
          type="button"
          onClick={onReindexSources}
          className="btn-outline sm:col-span-2"
        >
          Reindex sources
        </button>
      </div>
      {importMessage && <p className="mt-3 text-sm text-ink-soft">{importMessage}</p>}
      {reindexMessage && <p className="mt-2 text-sm text-ink-soft">{reindexMessage}</p>}
    </div>
  );
}
