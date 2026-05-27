import type { ProjectSummary } from "../../api";
import { authMode } from "../../api";
import { decisionLabel } from "../../utils/resultLabels";

export function SavedProjectsPanel({
  projects,
  projectsLoading,
  projectsMessage,
  onRefresh,
  onOpenProject,
}: {
  projects: ProjectSummary[];
  projectsLoading: boolean;
  projectsMessage: string;
  onRefresh: () => void;
  onOpenProject: (project: ProjectSummary) => void;
}) {
  if (authMode !== "supabase") {
    return null;
  }

  return (
    <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
          Saved Projects
        </p>
        <button
          type="button"
          onClick={onRefresh}
          className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500"
        >
          Refresh
        </button>
      </div>
      <div className="mt-4 space-y-3">
        {projectsLoading ? (
          <p className="text-sm text-slate-600">Loading projects...</p>
        ) : projects.length > 0 ? (
          projects.slice(0, 6).map((project) => (
            <button
              key={project.projectId}
              type="button"
              onClick={() => onOpenProject(project)}
              className="w-full rounded-2xl border border-slate-200 bg-slate-50 p-4 text-left transition hover:border-clay"
            >
              <p className="text-sm font-semibold text-slate-900">
                {project.normalizedAddress}
              </p>
              <p className="mt-1 text-xs uppercase tracking-[0.14em] text-slate-500">
                {project.jurisdictionName ?? project.jurisdictionId ?? "Unknown"} Â·{" "}
                {project.decision ? decisionLabel(project.decision) : project.status}
              </p>
            </button>
          ))
        ) : (
          <p className="text-sm leading-6 text-slate-600">
            Saved zoning reviews will appear here after your first run.
          </p>
        )}
        {projectsMessage && (
          <p className="text-sm leading-6 text-slate-600">{projectsMessage}</p>
        )}
      </div>
    </section>
  );
}
