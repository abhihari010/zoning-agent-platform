import type { Dispatch, RefObject, SetStateAction, KeyboardEvent } from "react";
import { authMode, type IntakeResponse, type JurisdictionCoverage } from "../../api";
import type { IntakeFacts, Phase } from "../../types/app";
import { coverageLabel } from "../../utils/resultLabels";

export function ProjectIntakePanel({
  phase,
  sourcesCount,
  acceptedDisclaimer,
  projectDescription,
  intakeFacts,
  address,
  suggestions,
  activeSuggestionIndex,
  suggestionLoading,
  addressSectionRef,
  publicSupportedCoverage,
  indexedCoverage,
  canSubmit,
  error,
  intake,
  jurisdictionRequestSubmitting,
  jurisdictionRequestMessage,
  onAcceptedDisclaimerChange,
  onProjectDescriptionChange,
  onIntakeFactsChange,
  onAddressChange,
  onAddressKeyDown,
  onSelectSuggestion,
  onSubmit,
  onReset,
  onRequestJurisdictionSupport,
}: {
  phase: Phase;
  sourcesCount: number;
  acceptedDisclaimer: boolean;
  projectDescription: string;
  intakeFacts: IntakeFacts;
  address: string;
  suggestions: string[];
  activeSuggestionIndex: number;
  suggestionLoading: boolean;
  addressSectionRef: RefObject<HTMLDivElement>;
  publicSupportedCoverage: JurisdictionCoverage[];
  indexedCoverage: JurisdictionCoverage[];
  canSubmit: boolean;
  error: string | null;
  intake: IntakeResponse | null;
  jurisdictionRequestSubmitting: boolean;
  jurisdictionRequestMessage: string;
  onAcceptedDisclaimerChange: (accepted: boolean) => void;
  onProjectDescriptionChange: (value: string) => void;
  onIntakeFactsChange: Dispatch<SetStateAction<IntakeFacts>>;
  onAddressChange: (value: string) => void;
  onAddressKeyDown: (event: KeyboardEvent<HTMLInputElement>) => void;
  onSelectSuggestion: (option: string) => void;
  onSubmit: () => void;
  onReset: () => void;
  onRequestJurisdictionSupport: () => void;
}) {
  return (
    <div className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
      <div className="mb-5 grid gap-4 rounded-3xl border border-slate-200 bg-slate-50/70 p-4 md:grid-cols-[minmax(0,1fr)_220px]">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
            Project Intake
          </p>
          <h2 className="mt-2 font-heading text-2xl text-pine">Tell us what you want to build</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Start with the project and the parcel address. The system will validate the
            property, infer the likely zoning context, and run the staged review.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3 md:grid-cols-1">
          <div className="rounded-2xl border border-slate-200 bg-white p-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              Stage
            </p>
            <p className="mt-2 text-sm font-semibold text-slate-900">
              {phase === "analyzing"
                ? "Analyzing"
                : phase === "intake"
                  ? "Validating"
                  : phase === "done"
                    ? "Ready"
                    : phase === "error"
                      ? "Error"
                      : "Waiting"}
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              Workflow
            </p>
            <p className="mt-2 text-sm font-semibold text-slate-900">5 stages</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              Registry
            </p>
            <p className="mt-2 text-sm font-semibold text-slate-900">{sourcesCount} sources</p>
          </div>
        </div>
      </div>

      <div className="mb-5 flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50/80 p-4 text-sm text-slate-700">
        <input
          className="mt-1 h-4 w-4 accent-clay"
          type="checkbox"
          checked={acceptedDisclaimer}
          onChange={(event) => onAcceptedDisclaimerChange(event.target.checked)}
        />
        <span>I understand this is an educational tool and not official legal approval.</span>
      </div>

      <label className="mb-4 block text-sm font-semibold text-slate-700">
        Describe the project
        <textarea
          className="mt-2 min-h-[160px] w-full rounded-2xl border border-slate-300 bg-slate-50/50 px-4 py-3 text-sm outline-none transition focus:border-clay focus:ring-2 focus:ring-clay"
          value={projectDescription}
          onChange={(event) => onProjectDescriptionChange(event.target.value)}
          placeholder="Example: Can I open a bakery out of my attached garage with two employees, weekday pickup hours, and limited interior renovation?"
        />
      </label>

      <IntakeFactsFields facts={intakeFacts} onFactsChange={onIntakeFactsChange} />

      <div ref={addressSectionRef}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label className="block text-sm font-semibold text-slate-700" htmlFor="address">
            Property address
          </label>
          <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-600">
            US addresses accepted; answers only where coverage is public-supported
          </span>
        </div>
        <input
          id="address"
          className="mt-2 w-full rounded-2xl border border-slate-300 bg-slate-50/50 px-4 py-3 text-sm outline-none transition focus:border-clay focus:ring-2 focus:ring-clay"
          value={address}
          onChange={(event) => onAddressChange(event.target.value)}
          onKeyDown={onAddressKeyDown}
          placeholder="123 Main St, Blacksburg, VA"
          autoComplete="off"
        />
        <div className="mt-3 flex flex-wrap gap-2">
          {publicSupportedCoverage.slice(0, 4).map((item) => (
            <span
              key={item.jurisdictionId}
              className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-900"
            >
              {item.name}
            </span>
          ))}
          {indexedCoverage.slice(0, 3).map((item) => (
            <span
              key={item.jurisdictionId}
              className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-900"
            >
              {item.name} source-indexed
            </span>
          ))}
        </div>

        {suggestionLoading && (
          <p className="mt-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
            Looking up addresses
          </p>
        )}

        {suggestions.length > 0 && (
          <ul className="mt-3 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50">
            {suggestions.map((option, index) => (
              <li key={`${option}-${index}`} className="border-b border-slate-200 last:border-b-0">
                <button
                  type="button"
                  onMouseDown={(event) => {
                    event.preventDefault();
                    onSelectSuggestion(option);
                  }}
                  onClick={() => onSelectSuggestion(option)}
                  className={`w-full px-4 py-3 text-left text-sm ${
                    index === activeSuggestionIndex ? "bg-amber-100" : "bg-transparent"
                  }`}
                >
                  {option}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <button
          type="button"
          onClick={onSubmit}
          disabled={!canSubmit || phase === "intake" || phase === "analyzing"}
          className="flex-1 rounded-2xl bg-gradient-to-r from-clay to-pine px-5 py-3 font-semibold text-white disabled:opacity-60"
        >
          {phase === "intake" || phase === "analyzing"
            ? "Running zoning review..."
            : "Run zoning review"}
        </button>
        <button
          type="button"
          onClick={onReset}
          className="rounded-2xl border border-slate-300 px-5 py-3 font-semibold text-slate-700"
        >
          Reset
        </button>
      </div>

      {error && (
        <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <p>{error}</p>
          {intake?.supportStatus === "unsupported" && (
            <div className="mt-4 rounded-2xl border border-amber-200 bg-white/80 p-4 text-amber-950">
              <p className="text-xs font-semibold uppercase tracking-[0.16em]">
                Request Coverage
              </p>
              <p className="mt-2 leading-6">
                We recognize {intake.jurisdictionName ?? "this jurisdiction"}, but it
                is {coverageLabel(intake.coverageStatus)} rather than public-supported.
              </p>
              <button
                type="button"
                onClick={onRequestJurisdictionSupport}
                disabled={jurisdictionRequestSubmitting || authMode !== "supabase"}
                className="mt-3 rounded-2xl bg-pine px-4 py-3 font-semibold text-white disabled:opacity-60"
              >
                {jurisdictionRequestSubmitting ? "Requesting..." : "Request support"}
              </button>
              {authMode !== "supabase" && (
                <p className="mt-2 text-xs leading-5">
                  Sign-in mode records demand by user; beta/local mode does not submit
                  coverage requests.
                </p>
              )}
              {jurisdictionRequestMessage && (
                <p className="mt-2 text-sm leading-6">{jurisdictionRequestMessage}</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function IntakeFactsFields({
  facts,
  onFactsChange,
}: {
  facts: IntakeFacts;
  onFactsChange: Dispatch<SetStateAction<IntakeFacts>>;
}) {
  return (
    <div className="mb-4 grid gap-4 rounded-3xl border border-slate-200 bg-slate-50/70 p-4 md:grid-cols-2">
      <label className="block text-sm font-semibold text-slate-700">
        Use type
        <select
          className="mt-2 w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm"
          value={facts.useType}
          onChange={(event) =>
            onFactsChange((current) => ({ ...current, useType: event.target.value }))
          }
        >
          <option value="">Select if known</option>
          <option value="Home-based food business">Home-based food business</option>
          <option value="Retail or service business">Retail or service business</option>
          <option value="Restaurant or cafe">Restaurant or cafe</option>
          <option value="Residential addition">Residential addition</option>
          <option value="General construction">General construction</option>
        </select>
      </label>
      <label className="block text-sm font-semibold text-slate-700">
        Construction scope
        <input
          className="mt-2 w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm"
          value={facts.constructionScope}
          onChange={(event) =>
            onFactsChange((current) => ({
              ...current,
              constructionScope: event.target.value,
            }))
          }
          placeholder="Interior renovation, addition, no construction"
        />
      </label>
      <label className="block text-sm font-semibold text-slate-700">
        Operating hours
        <input
          className="mt-2 w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm"
          value={facts.operatingHours}
          onChange={(event) =>
            onFactsChange((current) => ({
              ...current,
              operatingHours: event.target.value,
            }))
          }
          placeholder="Weekdays 8 AM to 5 PM"
        />
      </label>
      <label className="block text-sm font-semibold text-slate-700">
        Employees
        <input
          className="mt-2 w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm"
          value={facts.employeeCount}
          onChange={(event) =>
            onFactsChange((current) => ({
              ...current,
              employeeCount: event.target.value,
            }))
          }
          placeholder="Owner only, 2 employees, unknown"
        />
      </label>
      <label className="block text-sm font-semibold text-slate-700 md:col-span-2">
        Parking/loading
        <input
          className="mt-2 w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm"
          value={facts.parkingLoading}
          onChange={(event) =>
            onFactsChange((current) => ({
              ...current,
              parkingLoading: event.target.value,
            }))
          }
          placeholder="Existing driveway, deliveries twice weekly, customer pickup"
        />
      </label>
      <label className="flex items-start gap-3 text-sm font-semibold text-slate-700 md:col-span-2">
        <input
          className="mt-1 h-4 w-4 accent-clay"
          type="checkbox"
          checked={facts.foodFireHealth}
          onChange={(event) =>
            onFactsChange((current) => ({
              ...current,
              foodFireHealth: event.target.checked,
            }))
          }
        />
        Food, fire, or health department review may be triggered.
      </label>
    </div>
  );
}
