import { useState } from "react";
import { Link, Outlet } from "react-router-dom";
import type { LegalPage } from "../types/app";
import { LegalModal } from "../components/LegalModal";
import { BenchmarkMark } from "../components/WorkspaceHeader";

const LEGAL_PAGES: Array<{ key: Exclude<LegalPage, null>; label: string }> = [
  { key: "terms", label: "Terms" },
  { key: "privacy", label: "Privacy" },
  { key: "disclaimer", label: "Disclaimer" },
];

/**
 * Minimal dusk shell for /login and /signup: just the wordmark and the form,
 * centered on the warm-dark surface so signup carries the landing's tone
 * straight through to the product. Nothing competes for attention.
 */
export function AuthShell() {
  const [legalPage, setLegalPage] = useState<LegalPage>(null);

  return (
    <div className="dusk-bg flex min-h-[100dvh] flex-col">
      <div className="mx-auto flex w-full max-w-shell items-center px-4 py-6 md:px-8">
        <Link to="/" className="flex items-center gap-2.5" aria-label="Zoning Review home">
          <BenchmarkMark className="h-7 w-7" />
          <span className="font-display text-[15px] font-bold tracking-[-0.01em] text-paper">
            Zoning Review
          </span>
        </Link>
      </div>

      <main className="flex flex-1 items-center justify-center px-4 pb-16 pt-2">
        <div className="w-full max-w-[420px]">
          <Outlet />
        </div>
      </main>

      <footer className="pb-8">
        <div className="mx-auto flex max-w-shell flex-wrap items-center justify-center gap-x-5 gap-y-2 px-4">
          {LEGAL_PAGES.map((page) => (
            <button
              key={page.key}
              type="button"
              onClick={() => setLegalPage(page.key)}
              className="text-[12px] font-medium text-dusk-faint transition-colors duration-fast ease-out hover:text-dusk-soft"
            >
              {page.label}
            </button>
          ))}
        </div>
      </footer>

      {legalPage && (
        <LegalModal page={legalPage} onClose={() => setLegalPage(null)} />
      )}
    </div>
  );
}
