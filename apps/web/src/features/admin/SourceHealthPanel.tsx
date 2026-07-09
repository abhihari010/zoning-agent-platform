import type { SourceIndexStatus } from "../../api";
import { formatDateTime } from "../../utils/formatters";
import { readinessLabel } from "../../utils/resultLabels";

function HealthCell({
  label,
  value,
  note,
  tone = "neutral",
}: {
  label: string;
  value: string;
  note?: string;
  tone?: "neutral" | "ok" | "hold" | "stop";
}) {
  const valueColor =
    tone === "ok"
      ? "text-verdict-ok"
      : tone === "hold"
        ? "text-verdict-hold"
        : tone === "stop"
          ? "text-verdict-stop"
          : "text-ink";
  return (
    <div className="px-4 py-3.5">
      <p className="text-xs font-medium text-ink-faint">{label}</p>
      <p className={`tabular mt-1 truncate font-mono text-lg font-semibold ${valueColor}`}>
        {value}
      </p>
      {note && <p className="mt-0.5 truncate text-xs leading-5 text-ink-soft">{note}</p>}
    </div>
  );
}

function readinessToneKey(indexStatus: SourceIndexStatus | null): "neutral" | "ok" | "hold" | "stop" {
  if (!indexStatus) {
    return "neutral";
  }
  if (indexStatus.indexReady) {
    return "ok";
  }
  if (indexStatus.hasIndex) {
    return "hold";
  }
  return "stop";
}

export function SourceHealthPanel({
  indexStatus,
  sourceCount,
}: {
  indexStatus: SourceIndexStatus | null;
  sourceCount: number;
}) {
  const readiness = readinessToneKey(indexStatus);

  return (
    <div className="sheet p-6">
      <h2 className="sheet-title">Source health</h2>
      <div className="mt-4 grid grid-cols-2 divide-x divide-y divide-rule overflow-hidden rounded-sm border border-rule [&>*:nth-child(odd)]:!border-l-0 [&>*:nth-child(-n+2)]:!border-t-0">
        <HealthCell
          label="Readiness"
          value={readinessLabel(indexStatus)}
          note={
            indexStatus?.sourceRegistryVersion
              ? `Registry ${indexStatus.sourceRegistryVersion}`
              : "Registry version unset"
          }
          tone={readiness}
        />
        <HealthCell
          label="Sources"
          value={String(indexStatus?.sourceCount ?? sourceCount)}
        />
        <HealthCell
          label="Source packs"
          value={String(indexStatus?.sourcePackCount ?? 0)}
          note={(indexStatus?.sourcePackJurisdictionIds ?? []).join(", ") || "No packs found"}
        />
        <HealthCell
          label="Index chunks"
          value={String(indexStatus?.chunkCount ?? 0)}
          tone={readiness}
        />
        <HealthCell
          label="Vectors"
          value={String(indexStatus?.vectorCount ?? 0)}
          note={indexStatus?.vectorProvider ?? "none"}
          tone={indexStatus?.vectorIndexReady ? "ok" : "hold"}
        />
        <HealthCell label="Last import" value={formatDateTime(indexStatus?.lastImportAt)} />
        <HealthCell
          label="Last reindex"
          value={formatDateTime(indexStatus?.lastReindexAt)}
        />
        <HealthCell
          label="Automation"
          value={indexStatus ? (indexStatus.autoSeedSources ? "seed on" : "seed off") : "—"}
          note={
            indexStatus
              ? `Auto reindex empty: ${indexStatus.autoReindexOnEmpty ? "on" : "off"}`
              : undefined
          }
        />
      </div>
      {indexStatus && indexStatus.sourcesMissingMetadata.length > 0 && (
        <p className="mt-4 text-sm leading-6 text-verdict-hold">
          {indexStatus.sourcesMissingMetadata.length} source
          {indexStatus.sourcesMissingMetadata.length === 1 ? "" : "s"} need metadata before
          the index is fully auditable.
        </p>
      )}
      {indexStatus && (
        <div className="mt-4 space-y-3">
          {(indexStatus.staleSourceIds.length > 0 ||
            indexStatus.missingChunkSourceIds.length > 0) && (
            <div className="rounded-sm border border-verdict-hold/25 bg-verdict-holdwash p-4 text-sm">
              <p className="font-bold text-verdict-hold">Index refresh needed</p>
              {indexStatus.staleSourceIds.length > 0 && (
                <p className="mt-1.5 font-mono text-xs leading-5 text-ink-soft">
                  Stale: {indexStatus.staleSourceIds.join(", ")}
                </p>
              )}
              {indexStatus.missingChunkSourceIds.length > 0 && (
                <p className="mt-1.5 font-mono text-xs leading-5 text-ink-soft">
                  Missing chunks: {indexStatus.missingChunkSourceIds.join(", ")}
                </p>
              )}
            </div>
          )}
          {indexStatus.readinessWarnings.length > 0 && (
            <div className="rounded-sm border border-verdict-hold/25 bg-verdict-holdwash p-4 text-sm">
              <p className="font-bold text-verdict-hold">Readiness warnings</p>
              <ul className="mt-1.5 space-y-1 leading-6 text-ink-soft">
                {indexStatus.readinessWarnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
          {indexStatus.vectorReadinessWarnings.length > 0 && (
            <div className="rounded-sm border border-verdict-hold/25 bg-verdict-holdwash p-4 text-sm">
              <p className="font-bold text-verdict-hold">Vector warnings</p>
              <ul className="mt-1.5 space-y-1 leading-6 text-ink-soft">
                {indexStatus.vectorReadinessWarnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
