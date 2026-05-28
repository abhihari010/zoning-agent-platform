import type { Session } from "@supabase/supabase-js";
import { authMode, type CurrentUser } from "../api";
import { DISCLAIMER } from "../constants/legal";
import type { Workspace } from "../types/app";

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
  return (
    <section className="mb-5 grid gap-5 rounded-[28px] border border-pine/10 bg-white/90 p-6 shadow-card backdrop-blur lg:grid-cols-[minmax(0,1.5fr)_320px]">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
          Zoning Review Platform
        </p>
        <h1 className="mt-3 max-w-4xl font-heading text-3xl leading-tight text-pine md:text-[2.75rem]">
          Check whether a project is allowed on a property and get the next permit steps.
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-700 md:text-base">
          This workspace runs one orchestrated zoning pipeline: it understands the request,
          checks property context, retrieves municipal code evidence, and turns that into a
          feasibility summary plus a permit checklist.
        </p>
      </div>

      <div className="flex flex-col justify-between gap-4">
        <div className="rounded-3xl border border-amber-200 bg-amber-50/90 p-4 text-sm leading-6 text-amber-950">
          {DISCLAIMER}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => onWorkspaceChange("assistant")}
            className={`flex-1 rounded-2xl px-4 py-3 text-sm font-semibold ${
              workspace === "assistant"
                ? "bg-pine text-white"
                : "border border-slate-300 bg-white text-slate-700"
            }`}
          >
            Assistant
          </button>
          {canUseAdminTools && (
            <button
              type="button"
              onClick={() => onWorkspaceChange("admin")}
              className={`flex-1 rounded-2xl px-4 py-3 text-sm font-semibold ${
                workspace === "admin"
                  ? "bg-clay text-white"
                  : "border border-slate-300 bg-white text-slate-700"
              }`}
            >
              Source Admin
            </button>
          )}
        </div>
        {authMode === "supabase" && (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
            <p className="font-semibold text-slate-900">
              {currentUser?.email ?? authSession?.user.email ?? "Signed in"}
            </p>
            <div className="mt-2 flex items-center justify-between gap-3">
              <span className="text-xs uppercase tracking-[0.16em] text-slate-500">
                {currentUser?.role ?? "user"}
              </span>
              <button
                type="button"
                onClick={onSignOut}
                className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500"
              >
                Sign out
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
