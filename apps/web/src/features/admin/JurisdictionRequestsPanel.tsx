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
    <div className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
            Demand Backlog
          </p>
          <h2 className="mt-2 font-heading text-2xl text-pine">Jurisdiction Requests</h2>
        </div>
        <span className="rounded-full bg-mist px-3 py-1 text-xs font-semibold text-pine">
          {requests.length} queued
        </span>
      </div>
      <div className="mt-5 space-y-3">
        {loading ? (
          <p className="text-sm text-slate-600">Loading request backlog...</p>
        ) : message ? (
          <p className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
            {message}
          </p>
        ) : requests.length === 0 ? (
          <p className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-600">
            No jurisdiction requests have been logged yet.
          </p>
        ) : (
          requests.map((request) => {
            const matchedCoverage = coverageForRequest(request);
            const coverageStatus = matchedCoverage?.coverageStatus;
            const title =
              request.jurisdictionName ??
              request.jurisdictionId ??
              "Unknown jurisdiction";
            return (
              <article
                key={`${request.jurisdictionId ?? "unknown"}-${request.jurisdictionName ?? "unnamed"}-${request.state ?? "na"}`}
                className="rounded-2xl border border-slate-200 bg-slate-50 p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-slate-900">{title}</p>
                    <p className="mt-1 text-xs uppercase tracking-[0.14em] text-slate-500">
                      {formatLocationParts(request.state, request.county, request.locality)}
                    </p>
                  </div>
                  <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-700">
                    {request.requestCount} request{request.requestCount === 1 ? "" : "s"}
                  </span>
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded-full border px-3 py-1 text-xs font-semibold ${
                      matchedCoverage
                        ? coverageTone(coverageStatus)
                        : "border-slate-200 bg-white text-slate-600"
                    }`}
                  >
                    {matchedCoverage ? coverageLabel(coverageStatus) : "Coverage unknown"}
                  </span>
                  <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-600">
                    Last requested {formatDateTime(request.lastRequestedAt)}
                  </span>
                </div>
              </article>
            );
          })
        )}
      </div>
    </div>
  );
}
