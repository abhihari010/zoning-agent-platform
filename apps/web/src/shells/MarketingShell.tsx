import { useState } from "react";
import { Link, Outlet } from "react-router-dom";
import { motion } from "motion/react";
import { DISCLAIMER } from "../constants/legal";
import type { LegalPage } from "../types/app";
import { LegalModal } from "../components/LegalModal";
import { BenchmarkMark } from "../components/WorkspaceHeader";
import { useAuth } from "../auth/AuthContext";
import { useSmoothScroll } from "../lib/useSmoothScroll";
import { hoverLift } from "../lib/motion";

const NAV_LINKS = [
  { href: "#how", label: "How it works" },
  { href: "#preview", label: "The record" },
  { href: "#coverage", label: "Coverage" },
];

const LEGAL_PAGES: Array<{ key: Exclude<LegalPage, null>; label: string }> = [
  { key: "terms", label: "Terms" },
  { key: "privacy", label: "Privacy" },
  { key: "disclaimer", label: "Disclaimer" },
];

export function MarketingShell() {
  useSmoothScroll();
  const { isAuthenticated } = useAuth();
  const [legalPage, setLegalPage] = useState<LegalPage>(null);

  return (
    <div className="dusk-bg flex min-h-[100dvh] flex-col text-dusk-soft">
      <header className="sticky top-0 z-[var(--z-sticky)] border-b border-dusk-line bg-dusk/70 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-shell items-center gap-6 px-4 md:px-8">
          <Link
            to="/"
            className="flex items-center gap-2.5"
            aria-label="Zoning Review home"
          >
            <BenchmarkMark className="h-7 w-7" />
            <span className="font-display text-[15px] font-bold tracking-[-0.02em] text-paper">
              Zoning Review
            </span>
          </Link>

          <nav
            className="ml-2 hidden items-center gap-7 md:flex"
            aria-label="Sections"
          >
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="marketing-link-dusk"
              >
                {link.label}
              </a>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            {isAuthenticated ? (
              <motion.div {...hoverLift}>
                <Link to="/review" className="btn-primary min-h-11 px-4 py-2 text-sm">
                  Go to review
                </Link>
              </motion.div>
            ) : (
              <>
                <Link
                  to="/login"
                  className="marketing-link-dusk hidden sm:inline-block"
                >
                  Log in
                </Link>
                <motion.div {...hoverLift}>
                  <Link to="/signup" className="btn-primary min-h-11 px-4 py-2 text-sm">
                    Sign up
                  </Link>
                </motion.div>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-dusk-line bg-dusk-deep">
        <div className="mx-auto max-w-shell px-4 py-12 md:px-8">
          <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
            <div className="max-w-md">
              <Link to="/" className="flex items-center gap-2.5">
                <BenchmarkMark className="h-6 w-6" />
                <span className="font-display text-sm font-bold tracking-[-0.02em] text-paper">
                  Zoning Review
                </span>
              </Link>
              <p className="mt-3 text-xs leading-6 text-dusk-faint">
                {DISCLAIMER}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
              {LEGAL_PAGES.map((page) => (
                <button
                  key={page.key}
                  type="button"
                  onClick={() => setLegalPage(page.key)}
                  className="text-[13px] font-medium text-dusk-soft transition-colors duration-fast ease-out hover:text-paper"
                >
                  {page.label}
                </button>
              ))}
              <Link
                to="/login"
                className="text-[13px] font-medium text-dusk-soft hover:text-paper"
              >
                Log in
              </Link>
            </div>
          </div>
          <p className="mt-8 font-mono text-[11px] uppercase tracking-label text-dusk-faint">
            © {new Date().getFullYear()} Zoning Review · Feasibility records
          </p>
        </div>
      </footer>

      {legalPage && (
        <LegalModal page={legalPage} onClose={() => setLegalPage(null)} />
      )}
    </div>
  );
}
