import type { ProjectSummary } from "../../api";
import { authMode } from "../../api";
import { decisionLabel } from "../../utils/resultLabels";

export function SavedReviewsPage({
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
    <section className="enter enter-1 mx-auto max-w-[760px]">
      <div className="flex items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-display text-2xl font-bold tracking-[-0.01em] text-ink">
            Saved reviews
          </h1>
          <p className="mt-1.5 text-sm leading-6 text-ink-soft">
            Every determination you have run. Open one to reload its full case
            file and citations.
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="btn-quiet shrink-0 px-3 py-1.5 text-sm"
        >
          Refresh
        </button>
      </div>

      <div className="sheet mt-6 p-2">
        {projectsLoading ? (
          <p className="px-4 py-6 text-sm text-ink-soft">Loading reviews…</p>
        ) : projects.length > 0 ? (
          <ul className="divide-y divide-rule">
            {projects.map((project) => (
              <li key={project.projectId}>
                <button
                  type="button"
                  onClick={() => onOpenProject(project)}
                  className="group flex w-full items-center justify-between gap-4 rounded-sm px-4 py-3.5 text-left transition-colors duration-150 ease-out hover:bg-well"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-mono text-[13px] font-medium text-ink group-hover:text-spruce-bright">
                      {project.normalizedAddress}
                    </span>
                    <span className="mt-1 block text-xs text-ink-faint">
                      {project.jurisdictionName ??
                        project.jurisdictionId ??
                        "Unknown"}
                    </span>
                  </span>
                  <span className="shrink-0 font-mono text-[11px] uppercase tracking-wide text-ink-soft">
                    {project.decision
                      ? decisionLabel(project.decision)
                      : project.status}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-4 py-6 text-sm leading-6 text-ink-soft">
            No saved reviews yet. Run a feasibility review and it will appear
            here.
          </p>
        )}
      </div>

      {projectsMessage && (
        <p className="mt-3 text-sm leading-6 text-ink-soft">{projectsMessage}</p>
      )}
    </section>
  );
}
