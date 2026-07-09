import { DISCLAIMER } from "../constants/legal";
import type { LegalPage } from "../types/app";

const PAGES: Array<{ key: Exclude<LegalPage, null>; label: string }> = [
  { key: "terms", label: "Terms" },
  { key: "privacy", label: "Privacy" },
  { key: "disclaimer", label: "Disclaimer" },
];

export function LegalFooter({
  onSelectPage,
}: {
  onSelectPage: (page: Exclude<LegalPage, null>) => void;
}) {
  return (
    <footer className="mt-12 border-t border-rule pb-2 pt-4">
      <p className="text-xs leading-5 text-ink-faint">{DISCLAIMER}</p>
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2">
        <p className="font-mono text-[11px] uppercase tracking-wide text-ink-faint">
          Zoning Review
        </p>
        {PAGES.map((page) => (
          <button
            key={page.key}
            type="button"
            onClick={() => onSelectPage(page.key)}
            className="text-[13px] font-medium text-ink-soft transition-colors duration-fast ease-out hover:text-ink"
          >
            {page.label}
          </button>
        ))}
      </div>
    </footer>
  );
}

export function LegalLinks({
  onSelectPage,
}: {
  onSelectPage: (page: Exclude<LegalPage, null>) => void;
}) {
  return (
    <div className="mt-5 flex flex-wrap gap-4">
      {PAGES.map((page) => (
        <button
          key={page.key}
          type="button"
          onClick={() => onSelectPage(page.key)}
          className="text-[13px] font-medium text-ink-soft transition-colors duration-150 ease-out hover:text-ink"
        >
          {page.label}
        </button>
      ))}
    </div>
  );
}
