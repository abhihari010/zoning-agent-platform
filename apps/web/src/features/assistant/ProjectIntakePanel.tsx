import { useRef, useState } from "react";
import type { Dispatch, ReactNode, RefObject, SetStateAction, KeyboardEvent } from "react";
import { AnimatePresence, motion } from "motion/react";
import { authMode, type IntakeResponse, type JurisdictionCoverage } from "../../api";
import type { IntakeFacts, Phase } from "../../types/app";
import { coverageLabel } from "../../utils/resultLabels";

const EASE_OUT_EXPO = [0.16, 1, 0.3, 1] as const;

const EMPLOYEE_OPTIONS = ["Owner only", "2–5", "6+", "Not sure"];
const SCOPE_OPTIONS = [
  "No construction",
  "Interior renovation",
  "Addition",
  "New structure",
];
const FOOD_OPTIONS = ["Yes", "No", "Not sure"];

export function ProjectIntakePanel({
  phase,
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
  const busy = phase === "intake" || phase === "analyzing";
  const descriptionRef = useRef<HTMLTextAreaElement | null>(null);

  function autosizeDescription() {
    const el = descriptionRef.current;
    if (!el) {
      return;
    }
    el.style.height = "auto";
    el.style.height = `${Math.max(el.scrollHeight, 120)}px`;
  }

  return (
    <div className="sheet relative p-6 md:p-8">
      {busy && <span className="review-line" aria-hidden="true" />}

      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[1.75rem] font-bold leading-[1.1] tracking-[-0.02em] text-ink md:text-[2rem]">
            Check what you can build on a property
          </h1>
          <p className="mt-2 max-w-xl text-sm leading-6 text-ink-soft">
            Describe the project and give the parcel address; the review checks the
            local ordinance and returns a determination with citations.
          </p>
        </div>
        <span
          className={`stamp mt-1 shrink-0 px-3 py-1.5 text-[10px] tracking-[0.22em] ${
            busy
              ? "border-verdict-hold/60 text-verdict-hold"
              : "border-spruce/50 text-spruce-bright"
          }`}
        >
          {busy ? "In review" : "Ready"}
        </span>
      </div>

      <fieldset
        disabled={busy}
        className={`mt-7 min-w-0 space-y-6 border-0 p-0 transition-opacity duration-med ease-out ${
          busy ? "opacity-60" : "opacity-100"
        }`}
      >
        <div ref={addressSectionRef} className="relative">
          <label className="field-label" htmlFor="address">
            Property address
          </label>
          <input
            id="address"
            className="field"
            value={address}
            onChange={(event) => onAddressChange(event.target.value)}
            onKeyDown={onAddressKeyDown}
            placeholder="123 Main St, Blacksburg, VA"
            autoComplete="off"
          />
          <AnimatePresence>
            {suggestions.length > 0 && (
              <motion.ul
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.15, ease: EASE_OUT_EXPO }}
                className="absolute inset-x-0 top-full z-20 mt-1 overflow-hidden rounded-sm border border-rule-strong bg-sheet shadow-raised"
              >
                {suggestions.map((option, index) => (
                  <li key={`${option}-${index}`} className="border-b border-rule last:border-b-0">
                    <button
                      type="button"
                      onMouseDown={(event) => {
                        event.preventDefault();
                        onSelectSuggestion(option);
                      }}
                      onClick={() => onSelectSuggestion(option)}
                      className={`w-full px-3.5 py-2.5 text-left font-mono text-[13px] transition-colors duration-fast ease-out ${
                        index === activeSuggestionIndex
                          ? "bg-spruce-wash text-ink"
                          : "bg-transparent text-ink-soft hover:bg-well hover:text-ink"
                      }`}
                    >
                      {option}
                    </button>
                  </li>
                ))}
              </motion.ul>
            )}
          </AnimatePresence>
          <p className="mt-2 text-xs leading-5 text-ink-faint">
            {suggestionLoading
              ? "Looking up addresses…"
              : "US addresses only. Determinations require public ordinance coverage."}
          </p>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {publicSupportedCoverage.slice(0, 4).map((item) => (
              <span key={item.jurisdictionId} className="tag tag-ok">
                {item.name}
              </span>
            ))}
            {indexedCoverage.slice(0, 3).map((item) => (
              <span key={item.jurisdictionId} className="tag tag-neutral">
                {item.name} · indexing
              </span>
            ))}
          </div>
        </div>

        <div>
          <label className="field-label" htmlFor="project-description">
            Describe the project
          </label>
          <p className="mt-1 text-xs leading-5 text-ink-faint">
            Example: “Can I open a bakery out of my attached garage with two employees
            and weekday pickup hours?”
          </p>
          <textarea
            id="project-description"
            ref={descriptionRef}
            className="field min-h-[120px] resize-none overflow-hidden transition-[height,border-color,box-shadow] duration-med ease-inout"
            value={projectDescription}
            onChange={(event) => {
              onProjectDescriptionChange(event.target.value);
              autosizeDescription();
            }}
            placeholder="What do you want to build or run, and how will it operate?"
          />
        </div>

        <ProjectDetailsDisclosure facts={intakeFacts} onFactsChange={onIntakeFactsChange} />

        <div className="space-y-4 border-t border-rule pt-5">
          <AcknowledgmentCheckbox
            checked={acceptedDisclaimer}
            onChange={onAcceptedDisclaimerChange}
          />
          <div className="flex flex-col gap-2.5 sm:flex-row">
            <button
              type="button"
              onClick={onSubmit}
              disabled={!canSubmit || busy}
              className="btn-primary flex-1 py-3 text-[15px] transition-[transform,background-color,border-color,color,filter,opacity] duration-med"
            >
              <AnimatePresence mode="wait" initial={false}>
                <motion.span
                  key={busy ? "busy" : "idle"}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                >
                  {busy ? "Reviewing…" : "Run feasibility review"}
                </motion.span>
              </AnimatePresence>
            </button>
            <button type="button" onClick={onReset} className="btn-quiet py-3">
              Reset
            </button>
          </div>
        </div>
      </fieldset>

      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25, ease: EASE_OUT_EXPO }}
            className="overflow-hidden"
          >
            <div className="mt-6 rounded-sm border border-verdict-stop/25 bg-verdict-stopwash p-4 text-sm text-verdict-stop">
              <p className="leading-6">{error}</p>
              {intake?.supportStatus === "unsupported" && (
                <div className="mt-4 rounded-sm border border-rule bg-sheet p-4 text-ink">
                  <p className="font-medium">
                    {intake.jurisdictionName ?? "This jurisdiction"} is recognized, but its
                    coverage is {coverageLabel(intake.coverageStatus).toLowerCase()} rather
                    than public-supported.
                  </p>
                  <button
                    type="button"
                    onClick={onRequestJurisdictionSupport}
                    disabled={jurisdictionRequestSubmitting || authMode !== "supabase"}
                    className="btn-primary mt-3"
                  >
                    {jurisdictionRequestSubmitting ? "Requesting…" : "Request coverage"}
                  </button>
                  {authMode !== "supabase" && (
                    <p className="mt-2 text-xs leading-5 text-ink-faint">
                      Sign-in mode records demand by user; beta/local mode does not submit
                      coverage requests.
                    </p>
                  )}
                  {jurisdictionRequestMessage && (
                    <p className="mt-2 text-sm leading-6 text-ink-soft">
                      {jurisdictionRequestMessage}
                    </p>
                  )}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function AcknowledgmentCheckbox({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5 text-sm leading-6 text-ink-soft">
      <input
        type="checkbox"
        className="sr-only"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span
        aria-hidden="true"
        className={`mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border transition-colors duration-fast ease-out ${
          checked ? "border-spruce bg-spruce" : "border-rule-strong bg-sheet"
        }`}
      >
        <svg viewBox="0 0 12 12" className="h-3 w-3" fill="none">
          <path
            d="M2.5 6.5L5 9l4.5-6"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="check-draw stroke-paper"
            data-checked={checked}
          />
        </svg>
      </span>
      <span>I understand this is an educational tool, not legal approval or a permit.</span>
    </label>
  );
}

function ChipGroup({
  label,
  options,
  value,
  onSelect,
  children,
}: {
  label: string;
  options: string[];
  value: string;
  onSelect: (option: string) => void;
  children?: ReactNode;
}) {
  return (
    <div>
      <p className="field-label">{label}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {options.map((option) => {
          const isSelected = value === option;
          return (
            <button
              key={option}
              type="button"
              className="chip"
              aria-pressed={isSelected}
              onClick={() => onSelect(isSelected ? "" : option)}
            >
              {option}
            </button>
          );
        })}
        {children}
      </div>
    </div>
  );
}

const fieldVariants = {
  hidden: { opacity: 0, y: 4 },
  visible: { opacity: 1, y: 0 },
};

function ProjectDetailsDisclosure({
  facts,
  onFactsChange,
}: {
  facts: IntakeFacts;
  onFactsChange: Dispatch<SetStateAction<IntakeFacts>>;
}) {
  const [open, setOpen] = useState(false);
  const scopeIsCustom =
    facts.constructionScope.length > 0 && !SCOPE_OPTIONS.includes(facts.constructionScope);
  const [otherScope, setOtherScope] = useState(scopeIsCustom);

  const providedCount = [
    facts.useType,
    facts.constructionScope,
    facts.operatingHours,
    facts.employeeCount,
    facts.parkingLoading,
    facts.foodService,
  ].filter((value) => value.trim()).length;

  return (
    <div className="rounded-sm border border-rule">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="flex w-full items-center gap-2.5 px-4 py-3.5 text-left transition-colors duration-fast ease-out hover:bg-well"
      >
        <motion.svg
          viewBox="0 0 12 12"
          className="h-3 w-3 shrink-0 text-ink-faint"
          animate={{ rotate: open ? 90 : 0 }}
          transition={{ duration: 0.25, ease: EASE_OUT_EXPO }}
          aria-hidden="true"
        >
          <path d="M4 2l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </motion.svg>
        <span className="shrink-0 whitespace-nowrap text-sm font-medium text-ink">
          Add project details
        </span>
        <span className="text-sm text-ink-faint">
          {!open && providedCount > 0
            ? `${providedCount} of 6 provided`
            : "optional — improves confidence of the determination"}
        </span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.65, 0, 0.35, 1] }}
            className="overflow-hidden"
          >
            <motion.div
              initial="hidden"
              animate="visible"
              variants={{ visible: { transition: { staggerChildren: 0.04 } } }}
              className="space-y-5 border-t border-rule px-4 py-5"
            >
              <motion.label variants={fieldVariants} className="field-label block">
                Use type
                <select
                  className="field"
                  value={facts.useType}
                  onChange={(event) =>
                    onFactsChange((current) => ({ ...current, useType: event.target.value }))
                  }
                >
                  <option value="">Not sure yet</option>
                  <option value="Home-based food business">Home-based food business</option>
                  <option value="Retail or service business">Retail or service business</option>
                  <option value="Restaurant or cafe">Restaurant or cafe</option>
                  <option value="Residential addition">Residential addition</option>
                  <option value="General construction">General construction</option>
                </select>
              </motion.label>

              <motion.div variants={fieldVariants}>
                <ChipGroup
                  label="Employees"
                  options={EMPLOYEE_OPTIONS}
                  value={facts.employeeCount}
                  onSelect={(option) =>
                    onFactsChange((current) => ({ ...current, employeeCount: option }))
                  }
                />
              </motion.div>

              <motion.div variants={fieldVariants}>
                <ChipGroup
                  label="Construction scope"
                  options={SCOPE_OPTIONS}
                  value={otherScope ? "" : facts.constructionScope}
                  onSelect={(option) => {
                    setOtherScope(false);
                    onFactsChange((current) => ({ ...current, constructionScope: option }));
                  }}
                >
                  <button
                    type="button"
                    className="chip"
                    aria-pressed={otherScope}
                    onClick={() => {
                      setOtherScope((current) => !current);
                      onFactsChange((current) => ({ ...current, constructionScope: "" }));
                    }}
                  >
                    Other
                  </button>
                </ChipGroup>
                <AnimatePresence initial={false}>
                  {otherScope && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.25, ease: [0.65, 0, 0.35, 1] }}
                      className="overflow-hidden"
                    >
                      <input
                        className="field"
                        value={facts.constructionScope}
                        onChange={(event) =>
                          onFactsChange((current) => ({
                            ...current,
                            constructionScope: event.target.value,
                          }))
                        }
                        placeholder="Describe the construction scope"
                      />
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>

              <motion.label variants={fieldVariants} className="field-label block">
                Operating hours
                <input
                  className="field"
                  value={facts.operatingHours}
                  onChange={(event) =>
                    onFactsChange((current) => ({
                      ...current,
                      operatingHours: event.target.value,
                    }))
                  }
                  placeholder="e.g. Weekdays 8–5"
                />
              </motion.label>

              <motion.label variants={fieldVariants} className="field-label block">
                Parking and loading
                <input
                  className="field"
                  value={facts.parkingLoading}
                  onChange={(event) =>
                    onFactsChange((current) => ({
                      ...current,
                      parkingLoading: event.target.value,
                    }))
                  }
                  placeholder="e.g. existing driveway, weekly deliveries"
                />
              </motion.label>

              <motion.div variants={fieldVariants}>
                <ChipGroup
                  label="Does the project involve food preparation or service?"
                  options={FOOD_OPTIONS}
                  value={facts.foodService}
                  onSelect={(option) =>
                    onFactsChange((current) => ({ ...current, foodService: option }))
                  }
                />
              </motion.div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
