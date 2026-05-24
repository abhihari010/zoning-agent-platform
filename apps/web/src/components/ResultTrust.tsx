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

function trustTone(isReady: boolean): string {
  return isReady
    ? "border-emerald-200 bg-emerald-50 text-emerald-950"
    : "border-amber-200 bg-amber-50 text-amber-950";
}

function citationKey(citation: SourceCitation): string {
  return `${citation.sourceId}-${citation.chunkId ?? citation.sectionRef}`;
}

export function DecisionCard({
  result,
  label,
  tone,
}: {
  result: AnalyzeResponse;
  label: string;
  tone: string;
}) {
  return (
    <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
            Decision Center
          </p>
          <h2 className="mt-2 font-heading text-3xl text-pine">{label}</h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-700">
            {result.feasibility.summary}
          </p>
        </div>
        <div className={`rounded-3xl border px-4 py-3 text-center ${tone}`}>
          <p className="text-xs font-semibold uppercase tracking-[0.18em]">Confidence</p>
          <p className="mt-1 font-heading text-3xl">
            {percent(result.feasibility.confidence)}
          </p>
        </div>
      </div>
    </section>
  );
}

export function TrustIndicatorBar({ result }: { result: AnalyzeResponse }) {
  const trust = result.trustIndicators;
  const jurisdictionReady = Boolean(trust?.jurisdictionAnalyzed);
  const districtReady = Boolean(trust && trust.districtConfidence >= 0.7);
  const sourceReady = Boolean(trust && trust.sourceCount > 0 && trust.vectorReadiness);
  const citationReady = result.citations.length > 0;

  return (
    <section className="rounded-[28px] border border-pine/10 bg-white p-5 shadow-card">
      <div className="grid gap-3 md:grid-cols-4">
        <div className={`rounded-2xl border p-4 ${trustTone(jurisdictionReady)}`}>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] opacity-75">
            Jurisdiction
          </p>
          <p className="mt-2 font-semibold">
            {trust?.jurisdictionName ?? (jurisdictionReady ? "Resolved" : "Needs review")}
          </p>
          <p className="mt-1 text-xs leading-5 opacity-80">
            {trust?.jurisdictionSupported === false ? "Not supported yet" : "Coverage checked"}
          </p>
        </div>
        <div className={`rounded-2xl border p-4 ${trustTone(districtReady)}`}>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] opacity-75">
            District
          </p>
          <p className="mt-2 font-semibold">{trust?.zoningDistrict ?? "Unknown"}</p>
          <p className="mt-1 text-xs leading-5 opacity-80">
            {trust ? `${percent(trust.districtConfidence)} via ${trust.districtSource}` : "No signal"}
          </p>
        </div>
        <div className={`rounded-2xl border p-4 ${trustTone(sourceReady)}`}>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] opacity-75">
            Source Index
          </p>
          <p className="mt-2 font-semibold">
            {trust?.sourceCount ?? 0} source{trust?.sourceCount === 1 ? "" : "s"}
          </p>
          <p className="mt-1 text-xs leading-5 opacity-80">
            Updated {formatDate(trust?.lastSourceUpdate)}
          </p>
        </div>
        <div className={`rounded-2xl border p-4 ${trustTone(citationReady)}`}>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] opacity-75">
            Evidence
          </p>
          <p className="mt-2 font-semibold">
            {result.citations.length} cited excerpt{result.citations.length === 1 ? "" : "s"}
          </p>
          <p className="mt-1 text-xs leading-5 opacity-80">
            {result.citationValidation
              ? `${percent(result.citationValidation.citationCoverage)} validation coverage`
              : "Validation pending"}
          </p>
        </div>
      </div>
    </section>
  );
}

export function UnsupportedJurisdiction({ result }: { result: AnalyzeResponse }) {
  if (result.trustIndicators?.jurisdictionSupported !== false) {
    return null;
  }

  return (
    <section className="rounded-[28px] border border-amber-200 bg-amber-50 p-5 text-amber-950 shadow-card">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-800">
        Jurisdiction Not Covered
      </p>
      <p className="mt-2 text-sm leading-6">
        {result.trustIndicators.jurisdictionName ?? "This jurisdiction"} was recognized, but the
        source registry does not yet include enough local code coverage for an automated zoning
        conclusion.
      </p>
    </section>
  );
}

export function EvidencePanel({ citations }: { citations: SourceCitation[] }) {
  if (citations.length === 0) {
    return (
      <div className="rounded-[24px] border border-red-200 bg-red-50 p-5 text-sm text-red-900">
        <p className="font-semibold">No source excerpts were retrieved.</p>
        <p className="mt-2 leading-6">
          Keep the zoning answer unknown or low confidence until a planner verifies the parcel,
          district, permitted use table, and recent amendments.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {citations.map((citation) => (
        <article
          key={citationKey(citation)}
          className="rounded-2xl border border-slate-200 bg-slate-50 p-4"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="font-semibold text-slate-900">{citation.title}</p>
              <div className="mt-2 flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
                <span>{citation.sectionRef}</span>
                {citation.chunkId && <span>Chunk {citation.chunkId}</span>}
                {citation.jurisdictionId && <span>{citation.jurisdictionId}</span>}
              </div>
            </div>
            {citation.score != null && (
              <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-600">
                Score {citation.score.toFixed(2)}
              </span>
            )}
          </div>
          <p className="mt-3 text-sm leading-7 text-slate-700">{citation.excerpt}</p>
          <div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
            <span>Effective date: {citation.effectiveDate ?? "Not provided"}</span>
            <span>Source type: {citation.sourceType ?? "registry"}</span>
          </div>
          {citation.url && (
            <a
              className="mt-3 inline-flex text-sm font-semibold text-clay underline-offset-2 hover:underline"
              href={citation.url}
              target="_blank"
              rel="noreferrer"
            >
              Open source reference
            </a>
          )}
        </article>
      ))}
    </div>
  );
}
