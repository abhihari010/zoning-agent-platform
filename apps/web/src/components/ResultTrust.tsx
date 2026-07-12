import type { AnalyzeResponse, SourceCitation } from "@zoning-agent/shared-schema";

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatDate(value?: string | null): string {
  if (!value) {
    return "Not recorded";
  }
  return new Date(value).toLocaleDateString();
}

function citationKey(citation: SourceCitation): string {
  return `${citation.sourceId}-${citation.chunkId ?? citation.sectionRef}`;
}

function TrustCell({
  label,
  value,
  note,
  ready,
}: {
  label: string;
  value: string;
  note: string;
  ready: boolean;
}) {
  return (
    <div className="px-5 py-4">
      <p className="flex items-center gap-2 text-xs font-medium text-ink-faint">
        <span
          aria-hidden="true"
          className={`inline-block h-2 w-2 rounded-full ${
            ready ? "bg-verdict-ok" : "bg-verdict-hold"
          }`}
        />
        {label}
        <span className="sr-only">{ready ? "(verified)" : "(needs review)"}</span>
      </p>
      <p className="mt-1.5 truncate text-sm font-medium text-ink" title={value}>
        {value}
      </p>
      <p className="mt-0.5 text-xs leading-5 text-ink-soft">{note}</p>
    </div>
  );
}

export function TrustIndicatorBar({ result }: { result: AnalyzeResponse }) {
  const trust = result.trustIndicators;
  const jurisdictionReady = Boolean(trust?.jurisdictionAnalyzed);
  const districtReady = Boolean(trust && trust.districtConfidence >= 0.7);
  const sourceReady = Boolean(trust && trust.sourceCount > 0 && trust.vectorReadiness);
  const citationReady = result.citations.length > 0;

  return (
    <section className="sheet grid divide-y divide-rule sm:grid-cols-2 sm:divide-y-0 md:grid-cols-4 md:divide-x">
      <TrustCell
        label="Jurisdiction"
        value={trust?.jurisdictionName ?? (jurisdictionReady ? "Resolved" : "Needs review")}
        note={trust?.jurisdictionSupported === false ? "Not supported yet" : "Coverage checked"}
        ready={jurisdictionReady}
      />
      <TrustCell
        label="District"
        value={trust?.zoningDistrict ?? "Unknown"}
        note={
          trust
            ? `${percent(trust.districtConfidence)} via ${trust.districtSource}`
            : "No signal"
        }
        ready={districtReady}
      />
      <TrustCell
        label="Source index"
        value={`${trust?.sourceCount ?? 0} source${trust?.sourceCount === 1 ? "" : "s"}`}
        note={`Updated ${formatDate(trust?.lastSourceUpdate)}`}
        ready={sourceReady}
      />
      <TrustCell
        label="Evidence"
        value={`${result.citations.length} cited excerpt${result.citations.length === 1 ? "" : "s"}`}
        note={
          result.citationValidation
            ? `${percent(result.citationValidation.citationCoverage)} validation coverage`
            : "Validation pending"
        }
        ready={citationReady}
      />
    </section>
  );
}

export function UnsupportedJurisdiction({ result }: { result: AnalyzeResponse }) {
  if (result.trustIndicators?.jurisdictionSupported !== false) {
    return null;
  }

  return (
    <section className="rounded-sm border border-verdict-hold/30 bg-verdict-holdwash p-5">
      <p className="text-sm font-bold text-verdict-hold">Jurisdiction not covered</p>
      <p className="mt-1.5 text-sm leading-6 text-ink-soft">
        {result.trustIndicators.jurisdictionName ?? "This jurisdiction"} was recognized,
        but the source registry does not yet include enough local code coverage for an
        automated zoning conclusion.
      </p>
    </section>
  );
}

export function EvidencePanel({ citations }: { citations: SourceCitation[] }) {
  if (citations.length === 0) {
    return (
      <div className="rounded-sm border border-verdict-stop/25 bg-verdict-stopwash p-5 text-sm">
        <p className="font-bold text-verdict-stop">No source excerpts were retrieved.</p>
        <p className="mt-1.5 leading-6 text-ink-soft">
          Keep the zoning answer unknown or low confidence until a planner verifies the
          parcel, district, permitted use table, and recent amendments.
        </p>
      </div>
    );
  }

  return (
    <div className="divide-y divide-rule rounded-sm border border-rule">
      {citations.map((citation) => (
        <article key={citationKey(citation)} className="p-4 md:p-5">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <p className="font-medium text-ink">{citation.title}</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                <span className="tag tag-neutral">{citation.sectionRef}</span>
                {citation.chunkId && (
                  <span className="tag tag-neutral">chunk {citation.chunkId}</span>
                )}
                {citation.jurisdictionId && (
                  <span className="tag tag-neutral">{citation.jurisdictionId}</span>
                )}
              </div>
            </div>
            {citation.score != null && (
              <span className="tabular shrink-0 font-mono text-xs text-ink-faint">
                score {citation.score.toFixed(2)}
              </span>
            )}
          </div>
          <p className="mt-3 border-l-2 border-rule-strong pl-3 text-sm leading-6 text-ink-soft">
            {citation.excerpt}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-ink-faint">
            <span>Effective {citation.effectiveDate ?? "date not provided"}</span>
            <span>Type: {citation.sourceType ?? "registry"}</span>
            {citation.url && (
              <a
                className="font-medium text-spruce-bright underline-offset-2 hover:underline"
                href={citation.url}
                target="_blank"
                rel="noreferrer"
              >
                Open source reference
              </a>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}
