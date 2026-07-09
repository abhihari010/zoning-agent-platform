import type { JurisdictionCoverage, JurisdictionRequestSummary } from "../../api";
import { formatDateTime, formatLocationParts } from "../../utils/formatters";
import { coverageLabel, coverageTone } from "../../utils/resultLabels";

export function JurisdictionRequestsPanel({
  requests,
  loading,
  message,
  coverageForRequest,
}: {
  requests: JurisdictionRequestSummary[];
  loading: boolean;
  message: string;
  coverageForRequest: (request: JurisdictionRequestSummary) => JurisdictionCoverage | undefined;
}) {
  return (
    <div className="sheet p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="sheet-title">Jurisdiction requests</h2>
        <span className="tag tag-neutral">{requests.length} queued</span>
      </div>
      <div className="mt-4">
        {loading ? (
          <p className="text-sm text-ink-soft">Loading request backlog…</p>
        ) : message ? (
          <p className="rounded-sm border border-verdict-hold/25 bg-verdict-holdwash p-4 text-sm leading-6 text-ink-soft">
            {message}
          </p>
        ) : requests.length === 0 ? (
          <p className="text-sm leading-6 text-ink-soft">
            No jurisdiction requests have been logged yet.
          </p>
        ) : (
          <div className="divide-y divide-rule">
            {requests.map((request) => {
              const matchedCoverage = coverageForRequest(request);
              const coverageStatus = matchedCoverage?.coverageStatus;
              const title =
                request.jurisdictionName ??
                request.jurisdictionId ??
                "Unknown jurisdiction";
              return (
                <article
                  key={`${request.jurisdictionId ?? "unknown"}-${request.jurisdictionName ?? "unnamed"}-${request.state ?? "na"}`}
                  className="py-4 first:pt-0 last:pb-0"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-medium text-ink">{title}</p>
                      <p className="mt-0.5 text-xs text-ink-faint">
                        {formatLocationParts(request.state, request.county, request.locality)}
                      </p>
                    </div>
                    <span className="tabular shrink-0 font-mono text-xs text-ink-soft">
                      ×{request.requestCount}
                    </span>
                  </div>
                  <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                    <span
                      className={`tag ${matchedCoverage ? coverageTone(coverageStatus) : "tag-neutral"}`}
                    >
                      {matchedCoverage ? coverageLabel(coverageStatus) : "Coverage unknown"}
                    </span>
                    <span className="text-xs text-ink-faint">
                      Last requested {formatDateTime(request.lastRequestedAt)}
                    </span>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
