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
    <div className="sheet self-start p-6 md:p-8">
      <div className="flex items-center justify-between gap-3">
        <h2 className="sheet-title">Source catalog</h2>
        <span className="tabular font-mono text-xs text-ink-faint">
          {total > sources.length ? `${sources.length} / ${total}` : `${total} sources`}
        </span>
      </div>

      <div className="mt-4">
        {sourcesLoading ? (
          <p className="text-sm text-ink-soft">Loading sources…</p>
        ) : (
          <div className="divide-y divide-rule">
            {sources.map((source) => (
              <article key={source.sourceId} className="py-5 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium leading-6 text-ink">{source.title}</p>
                    <p className="mt-1 font-mono text-xs text-ink-faint">
                      {source.jurisdictionId ?? "no jurisdiction"} · {source.sourceId} ·{" "}
                      {source.sectionRef}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => onEditSource(source)}
                    className="btn-outline px-3 py-1.5 text-xs"
                  >
                    Edit
                  </button>
                </div>
                <SourceHealthBadges
                  missingFields={sourceHealthById.get(source.sourceId) ?? []}
                  indexIssues={sourceIndexIssuesById.get(source.sourceId) ?? []}
                />
                <p className="mt-2.5 text-sm leading-6 text-ink-soft">{source.excerpt}</p>
              </article>
            ))}
          </div>
        )}
      </div>

      {!sourcesLoading && hasMore && (
        <div className="mt-5 flex justify-center border-t border-rule pt-5">
          <button
            type="button"
            onClick={onLoadMore}
            disabled={loadingMore}
            className="btn-outline"
          >
            {loadingMore ? "Loading…" : `Load more (${total - sources.length} remaining)`}
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
      <div className="mt-2 flex">
        <span className="tag tag-ok">Metadata complete</span>
      </div>
    );
  }

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {indexIssues.map((issue) => (
        <span key={issue} className="tag tag-hold">
          {issue}
        </span>
      ))}
      {missingFields.map((field) => (
        <span key={field} className="tag tag-hold">
          Missing {field.replace(/_/g, " ")}
        </span>
      ))}
    </div>
  );
}
