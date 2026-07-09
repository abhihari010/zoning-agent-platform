import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { authMode } from "../api";
import { useAuth } from "../auth/AuthContext";
import { BenchmarkMark } from "../components/WorkspaceHeader";

/**
 * Gates the product surfaces (/review, /admin). Off Supabase every visitor is
 * treated as authenticated. On Supabase, unauthenticated visitors are bounced
 * to /login carrying a `next` param so they land back where they were headed.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { authLoading, isAuthenticated } = useAuth();
  const location = useLocation();

  if (authMode === "supabase" && authLoading) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center">
        <div className="flex items-center gap-3 text-ink-soft">
          <BenchmarkMark className="h-6 w-6 animate-pulse" />
          <span className="font-mono text-[11px] uppercase tracking-[0.14em]">
            Loading records…
          </span>
        </div>
      </div>
    );
  }

  if (authMode === "supabase" && !isAuthenticated) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  return <>{children}</>;
}
