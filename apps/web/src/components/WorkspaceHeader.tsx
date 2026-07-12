import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Link } from "react-router-dom";
import type { Session } from "@supabase/supabase-js";
import { authMode, type CurrentUser } from "../api";
import type { Workspace } from "../types/app";

export function BenchmarkMark({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <rect width="32" height="32" rx="2" className="fill-spruce" />
      <circle cx="16" cy="16" r="7" fill="none" className="stroke-dusk" strokeWidth="2" />
      <path
        d="M16 3v6M16 23v6M3 16h6M23 16h6"
        className="stroke-dusk"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

const WORKSPACE_TABS: Array<{ key: Workspace; label: string }> = [
  { key: "assistant", label: "Review" },
  { key: "saved", label: "Saved reviews" },
  { key: "admin", label: "Source admin" },
];

function initialsFor(email?: string | null): string {
  if (!email) {
    return "ZR";
  }
  const handle = email.split("@")[0] ?? email;
  const parts = handle.split(/[.\-_]/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return handle.slice(0, 2).toUpperCase();
}

function AccountMenu({
  currentUser,
  authSession,
  onSignOut,
}: {
  currentUser: CurrentUser | null;
  authSession: Session | null;
  onSignOut: () => void;
}) {
  const [open, setOpen] = useState(false);
  const email = currentUser?.email ?? authSession?.user.email ?? "Signed in";
  const role = currentUser?.role ?? "user";

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-sm border border-rule-strong bg-sheet px-1.5 py-1.5 transition-colors duration-fast ease-out hover:border-ink-faint"
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-sm bg-spruce font-display text-[11px] font-bold text-white">
          {initialsFor(email)}
        </span>
        <span className="hidden max-w-[160px] truncate text-sm text-ink sm:block">
          {email}
        </span>
        <svg viewBox="0 0 12 12" className="mr-0.5 h-3 w-3 text-ink-faint" aria-hidden="true">
          <path d="M3 4.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      <AnimatePresence>
        {open && (
          <>
            <button
              type="button"
              aria-hidden="true"
              tabIndex={-1}
              onClick={() => setOpen(false)}
              className="fixed inset-0 z-30 cursor-default"
            />
            <motion.div
              role="menu"
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
              className="absolute right-0 z-40 mt-2 w-60 overflow-hidden rounded-sm border border-rule-strong bg-sheet shadow-raised"
            >
              <div className="border-b border-rule bg-well/60 px-4 py-3">
                <p className="truncate text-sm font-medium text-ink">{email}</p>
                <p className="font-mono text-[11px] uppercase tracking-wide text-ink-faint">
                  {role}
                </p>
              </div>
              <div className="p-1.5">
                <Link
                  to="/"
                  role="menuitem"
                  onClick={() => setOpen(false)}
                  className="block rounded-sm px-3 py-2 text-sm text-ink-soft transition-colors duration-fast hover:bg-well hover:text-ink"
                >
                  Home
                </Link>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setOpen(false);
                    onSignOut();
                  }}
                  className="block w-full rounded-sm px-3 py-2 text-left text-sm text-ink-soft transition-colors duration-fast hover:bg-well hover:text-ink"
                >
                  Sign out
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

export function WorkspaceHeader({
  workspace,
  canUseAdminTools,
  currentUser,
  authSession,
  onWorkspaceChange,
  onSignOut,
}: {
  workspace: Workspace;
  canUseAdminTools: boolean;
  currentUser: CurrentUser | null;
  authSession: Session | null;
  onWorkspaceChange: (workspace: Workspace) => void;
  onSignOut: () => void;
}) {
  // Review is always shown; Saved reviews needs Supabase-backed accounts, and
  // Source admin is admin-only. Hide the whole nav when only Review qualifies.
  const visibleTabs = WORKSPACE_TABS.filter((tab) => {
    if (tab.key === "saved") return authMode === "supabase";
    if (tab.key === "admin") return canUseAdminTools;
    return true;
  });

  return (
    <header className="relative z-40 border-b border-rule bg-sheet">
      <div className="mx-auto flex max-w-[1040px] flex-wrap items-stretch gap-x-8 gap-y-0 px-4 md:px-6">
        <Link to="/" className="flex items-center gap-3 py-3.5" aria-label="Zoning Review home">
          <BenchmarkMark className="h-7 w-7" />
          <p className="font-display text-[15px] font-bold tracking-[-0.01em] text-ink">
            Zoning Review
          </p>
        </Link>

        {visibleTabs.length > 1 && (
          <nav className="flex items-stretch" aria-label="Workspace">
            {visibleTabs.map((tab) => {
              const isActive = workspace === tab.key;
              return (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => onWorkspaceChange(tab.key)}
                  aria-current={isActive ? "page" : undefined}
                  className={`relative px-3.5 text-sm font-medium transition-colors duration-fast ease-out ${
                    isActive ? "text-ink" : "text-ink-soft hover:text-ink"
                  }`}
                >
                  {tab.label}
                  {isActive && (
                    <motion.span
                      layoutId="workspace-tab-underline"
                      className="absolute inset-x-3.5 -bottom-px h-0.5 bg-ink"
                      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                    />
                  )}
                </button>
              );
            })}
          </nav>
        )}

        {authMode === "supabase" && (
          <div className="ml-auto flex items-center py-2.5">
            <AccountMenu
              currentUser={currentUser}
              authSession={authSession}
              onSignOut={onSignOut}
            />
          </div>
        )}
      </div>
    </header>
  );
}
