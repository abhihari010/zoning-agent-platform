import type { SourceRegistryEntry } from "../../api";

export function SourceCatalog({
  sources,
  sourcesLoading,
  sourceHealthById,
  sourceIndexIssuesById,
  onEditSource,
  total,
  onLoadMore,
  loadingMore,
}: {
  sources: SourceRegistryEntry[];
  sourcesLoading: boolean;
  sourceHealthById: Map<string, string[]>;
  sourceIndexIssuesById: Map<string, string[]>;
  onEditSource: (source: SourceRegistryEntry) => void;
  total: number;
  onLoadMore: () => void;
  loadingMore: boolean;
}) {
  const hasMore = sources.length < total;
  return (
    <div className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
            Registered Sources
          </p>
          <h2 className="mt-2 font-heading text-2xl text-pine">Catalog</h2>
        </div>
        <span className="rounded-full bg-mist px-3 py-1 text-xs font-semibold text-pine">
          {total > sources.length
            ? `${sources.length} of ${total} sources`
            : `${total} sources`}
        </span>
      </div>

      <div className="mt-5 space-y-3">
        {sourcesLoading ? (
          <p className="text-sm text-slate-600">Loading sources...</p>
        ) : (
          sources.map((source) => (
            <article
              key={source.sourceId}
              className="rounded-3xl border border-slate-200 bg-slate-50 p-5"
            >
              <SourceHealthBadges
                missingFields={sourceHealthById.get(source.sourceId) ?? []}
                indexIssues={sourceIndexIssuesById.get(source.sourceId) ?? []}
              />
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-semibold text-slate-900">{source.title}</p>
                  <p className="mt-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
                    {source.jurisdictionId ?? "No jurisdiction"}
                  </p>
                  <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-500">
                    {source.sourceId} Â· {source.sectionRef}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => onEditSource(source)}
                  className="rounded-2xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700"
                >
                  Edit
                </button>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-700">{source.excerpt}</p>
            </article>
          ))
        )}
      </div>

      {!sourcesLoading && hasMore && (
        <div className="mt-5 flex justify-center">
          <button
            type="button"
            onClick={onLoadMore}
            disabled={loadingMore}
            className="rounded-2xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-60"
          >
            {loadingMore ? "Loading..." : `Load more (${total - sources.length} remaining)`}
          </button>
        </div>
      )}
    </div>
  );
}

function SourceHealthBadges({
  missingFields,
  indexIssues,
}: {
  missingFields: string[];
  indexIssues: string[];
}) {
  const hasIssues = missingFields.length > 0 || indexIssues.length > 0;
  if (!hasIssues) {
    return (
      <div className="mb-3 inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-900">
        Metadata complete
      </div>
    );
  }

  return (
    <div className="mb-3 flex flex-wrap gap-2">
      {indexIssues.map((issue) => (
        <span
          key={issue}
          className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-900"
        >
          {issue}
        </span>
      ))}
      {missingFields.map((field) => (
        <span
          key={field}
          className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-900"
        >
          Missing {field.replace(/_/g, " ")}
        </span>
      ))}
    </div>
  );
}
