import type { Dispatch, SetStateAction } from "react";
import type { SourceRegistryEntry } from "../../api";
import { parseTagList } from "../../utils/sourceForms";

export function SourceEditorForm({
  sourceForm,
  setSourceForm,
  sourceSaving,
  sourceMessage,
  onSaveSource,
}: {
  sourceForm: SourceRegistryEntry;
  setSourceForm: Dispatch<SetStateAction<SourceRegistryEntry>>;
  sourceSaving: boolean;
  sourceMessage: string;
  onSaveSource: () => void;
}) {
  return (
    <div className="sheet p-6">
      <h2 className="sheet-title">Source editor</h2>
      <div className="mt-4 space-y-4">
        <label className="field-label">
          Source ID
          <input
            className="field font-mono"
            value={sourceForm.sourceId}
            onChange={(event) =>
              setSourceForm((current) => ({ ...current, sourceId: event.target.value }))
            }
          />
        </label>
        <label className="field-label">
          Title
          <input
            className="field"
            value={sourceForm.title}
            onChange={(event) =>
              setSourceForm((current) => ({ ...current, title: event.target.value }))
            }
          />
        </label>
        <label className="field-label">
          Excerpt
          <textarea
            className="field min-h-[130px]"
            value={sourceForm.excerpt}
            onChange={(event) =>
              setSourceForm((current) => ({ ...current, excerpt: event.target.value }))
            }
          />
        </label>
        <label className="field-label">
          Section reference
          <input
            className="field font-mono"
            value={sourceForm.sectionRef}
            onChange={(event) =>
              setSourceForm((current) => ({ ...current, sectionRef: event.target.value }))
            }
          />
        </label>
        <label className="field-label">
          Jurisdiction ID
          <input
            className="field font-mono"
            value={sourceForm.jurisdictionId ?? ""}
            onChange={(event) =>
              setSourceForm((current) => ({
                ...current,
                jurisdictionId: event.target.value,
              }))
            }
            placeholder="blacksburg-va"
          />
        </label>
        <label className="field-label">
          URL
          <input
            className="field font-mono"
            value={sourceForm.url ?? ""}
            onChange={(event) =>
              setSourceForm((current) => ({ ...current, url: event.target.value }))
            }
          />
        </label>
        <label className="field-label">
          Effective date
          <input
            className="field font-mono"
            value={sourceForm.effectiveDate ?? ""}
            onChange={(event) =>
              setSourceForm((current) => ({
                ...current,
                effectiveDate: event.target.value,
              }))
            }
          />
        </label>
        <label className="field-label">
          Districts
          <input
            className="field font-mono"
            value={sourceForm.districts.join(", ")}
            onChange={(event) =>
              setSourceForm((current) => ({
                ...current,
                districts: parseTagList(event.target.value),
              }))
            }
          />
        </label>
        <label className="field-label">
          Uses
          <input
            className="field"
            value={sourceForm.uses.join(", ")}
            onChange={(event) =>
              setSourceForm((current) => ({
                ...current,
                uses: parseTagList(event.target.value),
              }))
            }
          />
        </label>
      </div>

      <button
        type="button"
        onClick={onSaveSource}
        disabled={sourceSaving}
        className="btn-primary mt-5 w-full"
      >
        {sourceSaving ? "Saving…" : "Save source"}
      </button>
      {sourceMessage && <p className="mt-3 text-sm text-ink-soft">{sourceMessage}</p>}
    </div>
  );
}
