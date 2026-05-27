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
    <div className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
        Source Editor
      </p>
      <div className="mt-4 space-y-4">
        <label className="block text-sm font-semibold text-slate-700">
          Source ID
          <input
            className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
            value={sourceForm.sourceId}
            onChange={(event) =>
              setSourceForm((current) => ({ ...current, sourceId: event.target.value }))
            }
          />
        </label>
        <label className="block text-sm font-semibold text-slate-700">
          Title
          <input
            className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
            value={sourceForm.title}
            onChange={(event) =>
              setSourceForm((current) => ({ ...current, title: event.target.value }))
            }
          />
        </label>
        <label className="block text-sm font-semibold text-slate-700">
          Excerpt
          <textarea
            className="mt-2 min-h-[140px] w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
            value={sourceForm.excerpt}
            onChange={(event) =>
              setSourceForm((current) => ({ ...current, excerpt: event.target.value }))
            }
          />
        </label>
        <label className="block text-sm font-semibold text-slate-700">
          Section reference
          <input
            className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
            value={sourceForm.sectionRef}
            onChange={(event) =>
              setSourceForm((current) => ({ ...current, sectionRef: event.target.value }))
            }
          />
        </label>
        <label className="block text-sm font-semibold text-slate-700">
          Jurisdiction ID
          <input
            className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
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
        <label className="block text-sm font-semibold text-slate-700">
          URL
          <input
            className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
            value={sourceForm.url ?? ""}
            onChange={(event) =>
              setSourceForm((current) => ({ ...current, url: event.target.value }))
            }
          />
        </label>
        <label className="block text-sm font-semibold text-slate-700">
          Effective date
          <input
            className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
            value={sourceForm.effectiveDate ?? ""}
            onChange={(event) =>
              setSourceForm((current) => ({
                ...current,
                effectiveDate: event.target.value,
              }))
            }
          />
        </label>
        <label className="block text-sm font-semibold text-slate-700">
          Districts
          <input
            className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
            value={sourceForm.districts.join(", ")}
            onChange={(event) =>
              setSourceForm((current) => ({
                ...current,
                districts: parseTagList(event.target.value),
              }))
            }
          />
        </label>
        <label className="block text-sm font-semibold text-slate-700">
          Uses
          <input
            className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
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
        className="mt-5 w-full rounded-2xl bg-clay px-4 py-3 font-semibold text-white disabled:opacity-60"
      >
        {sourceSaving ? "Saving..." : "Save source"}
      </button>
      {sourceMessage && <p className="mt-4 text-sm text-slate-700">{sourceMessage}</p>}
    </div>
  );
}
