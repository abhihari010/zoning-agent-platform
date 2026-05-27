import type { SourceIndexStatus } from "../../api";
import { formatDateTime } from "../../utils/formatters";
import { readinessLabel, readinessTone } from "../../utils/resultLabels";

export function SourceHealthPanel({
  indexStatus,
  sourceCount,
}: {
  indexStatus: SourceIndexStatus | null;
  sourceCount: number;
}) {
  return (
    <div className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
        Source Health
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className={`rounded-2xl border p-4 ${readinessTone(indexStatus)}`}>
          <p className="text-xs uppercase tracking-[0.18em] opacity-75">Readiness</p>
          <p className="mt-2 text-2xl font-semibold">{readinessLabel(indexStatus)}</p>
          <p className="mt-1 text-xs font-semibold uppercase tracking-[0.14em] opacity-80">
            {indexStatus?.sourceRegistryVersion
              ? `Registry ${indexStatus.sourceRegistryVersion}`
              : "Registry version unset"}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Sources</p>
          <p className="mt-2 text-2xl font-semibold text-pine">
            {indexStatus?.sourceCount ?? sourceCount}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Source Packs</p>
          <p className="mt-2 text-2xl font-semibold text-pine">
            {indexStatus?.sourcePackCount ?? 0}
          </p>
          <p className="mt-1 text-xs leading-5 text-slate-600">
            {(indexStatus?.sourcePackJurisdictionIds ?? []).join(", ") || "No packs found"}
          </p>
        </div>
        <div className={`rounded-2xl border p-4 ${readinessTone(indexStatus)}`}>
          <p className="text-xs uppercase tracking-[0.18em] opacity-75">Index</p>
          <p className="mt-2 text-2xl font-semibold">{indexStatus?.chunkCount ?? 0} chunks</p>
        </div>
        <div
          className={`rounded-2xl border p-4 ${
            indexStatus?.vectorIndexReady
              ? "border-emerald-200 bg-emerald-50 text-emerald-950"
              : "border-amber-200 bg-amber-50 text-amber-950"
          }`}
        >
          <p className="text-xs uppercase tracking-[0.18em] opacity-75">Vectors</p>
          <p className="mt-2 text-2xl font-semibold">{indexStatus?.vectorCount ?? 0} vectors</p>
          <p className="mt-1 text-xs font-semibold uppercase tracking-[0.14em] opacity-80">
            {indexStatus?.vectorProvider ?? "none"}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Last import</p>
          <p className="mt-2 text-sm font-semibold text-slate-900">
            {formatDateTime(indexStatus?.lastImportAt)}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Last reindex</p>
          <p className="mt-2 text-sm font-semibold text-slate-900">
            {formatDateTime(indexStatus?.lastReindexAt)}
          </p>
        </div>
      </div>
      {indexStatus && indexStatus.sourcesMissingMetadata.length > 0 && (
        <p className="mt-4 text-sm leading-6 text-amber-900">
          {indexStatus.sourcesMissingMetadata.length} source
          {indexStatus.sourcesMissingMetadata.length === 1 ? "" : "s"} need metadata before the
          index is fully auditable.
        </p>
      )}
      {indexStatus && (
        <div className="mt-4 grid gap-3">
          {(indexStatus.staleSourceIds.length > 0 ||
            indexStatus.missingChunkSourceIds.length > 0) && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
              <p className="font-semibold">Index refresh needed</p>
              {indexStatus.staleSourceIds.length > 0 && (
                <p className="mt-2 leading-6">
                  Stale sources: {indexStatus.staleSourceIds.join(", ")}
                </p>
              )}
              {indexStatus.missingChunkSourceIds.length > 0 && (
                <p className="mt-2 leading-6">
                  Missing chunks: {indexStatus.missingChunkSourceIds.join(", ")}
                </p>
              )}
            </div>
          )}
          {indexStatus.readinessWarnings.length > 0 && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
              <p className="font-semibold">Readiness warnings</p>
              <ul className="mt-2 space-y-1 leading-6">
                {indexStatus.readinessWarnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
          {indexStatus.vectorReadinessWarnings.length > 0 && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
              <p className="font-semibold">Vector warnings</p>
              <ul className="mt-2 space-y-1 leading-6">
                {indexStatus.vectorReadinessWarnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-xs leading-5 text-slate-600">
            Auto seed: {indexStatus.autoSeedSources ? "on" : "off"} Â· Auto reindex empty:{" "}
            {indexStatus.autoReindexOnEmpty ? "on" : "off"}
          </div>
        </div>
      )}
    </div>
  );
}
