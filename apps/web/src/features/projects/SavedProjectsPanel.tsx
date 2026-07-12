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
    <section className="sheet p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-bold text-ink">Saved reviews</h2>
        <button type="button" onClick={onRefresh} className="btn-quiet px-2 py-1 text-xs">
          Refresh
        </button>
      </div>
      <div className="mt-3">
        {projectsLoading ? (
          <p className="text-sm text-ink-soft">Loading projects…</p>
        ) : projects.length > 0 ? (
          <ul className="divide-y divide-rule">
            {projects.slice(0, 6).map((project) => (
              <li key={project.projectId}>
                <button
                  type="button"
                  onClick={() => onOpenProject(project)}
                  className="group w-full py-3 text-left transition-colors duration-150 ease-out first:pt-0"
                >
                  <p className="truncate font-mono text-[13px] font-medium text-ink group-hover:text-spruce-bright">
                    {project.normalizedAddress}
                  </p>
                  <p className="mt-1 text-xs text-ink-faint">
                    {project.jurisdictionName ?? project.jurisdictionId ?? "Unknown"}
                    {" · "}
                    {project.decision ? decisionLabel(project.decision) : project.status}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm leading-6 text-ink-soft">
            Saved zoning reviews will appear here after your first run.
          </p>
        )}
        {projectsMessage && (
          <p className="mt-2 text-sm leading-6 text-ink-soft">{projectsMessage}</p>
        )}
      </div>
    </section>
  );
}
