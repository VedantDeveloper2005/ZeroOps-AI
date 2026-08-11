"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Bot,
  CheckCircle2,
  GitBranch,
  Loader2,
  Rocket,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { ProjectTabs } from "@/components/dashboard/ProjectTabs";
import { useNotifications } from "@/lib/NotificationContext";
import { api, getErrorMessage, type ProjectActivity } from "@/lib/api";

function iconForAction(action: string) {
  const normalized = action.toLowerCase();
  if (normalized.includes("deploy") || normalized.includes("release")) return Rocket;
  if (normalized.includes("analysis") || normalized.includes("plan")) return Bot;
  if (normalized.includes("security") || normalized.includes("secret")) return ShieldCheck;
  if (normalized.includes("repository") || normalized.includes("branch")) return GitBranch;
  if (normalized.includes("user") || normalized.includes("member")) return UserRound;
  return CheckCircle2;
}

function formatTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Time not recorded";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function ActivityPage() {
  return (
    <Suspense fallback={<ActivityPageLoading />}>
      <ActivityWorkspace />
    </Suspense>
  );
}

function ActivityWorkspace() {
  const searchParams = useSearchParams();
  const { projects, isLoading: projectsLoading } = useNotifications();
  const [selectedProjectId, setSelectedProjectId] = useState("all");
  const [activity, setActivity] = useState<ProjectActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const selectedProject = projects.find(
    (project) => project.id === selectedProjectId,
  );

  useEffect(() => {
    const requestedProject = searchParams.get("project");
    if (requestedProject && projects.some((project) => project.id === requestedProject)) {
      setSelectedProjectId(requestedProject);
    }
  }, [projects, searchParams]);

  useEffect(() => {
    if (projectsLoading) return;
    let cancelled = false;

    async function loadActivity() {
      setLoading(true);
      setError(null);
      try {
        const records =
          selectedProjectId === "all"
            ? await api.getGlobalActivity()
            : await api.getProjectActivity(selectedProjectId);
        if (!cancelled) setActivity(records);
      } catch (loadError) {
        if (!cancelled) {
          setActivity([]);
          setError(getErrorMessage(loadError, "Activity history could not be loaded."));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadActivity();
    return () => {
      cancelled = true;
    };
  }, [projectsLoading, selectedProjectId]);

  return (
    <div className="pb-8">
      <PageHeader
        eyebrow="Audit history"
        title="Activity"
        description="A chronological record of repository, analysis, plan, deployment, and configuration events persisted by the backend."
        actions={
          projects.length > 0 ? (
            <div className="w-full sm:w-72">
              <label>
                <span className="sr-only">Filter activity by project</span>
                <select
                  value={selectedProjectId}
                  onChange={(event) => setSelectedProjectId(event.target.value)}
                  className="min-h-11 w-full rounded-lg border border-border bg-card px-3 text-sm font-medium text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
                >
                  <option value="all">All projects</option>
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ) : undefined
        }
      />

      {selectedProject && (
        <div className="mb-6">
          <ProjectTabs projectId={selectedProject.id} />
        </div>
      )}

      {error ? (
        <StatePanel
          variant="error"
          title="Activity history is unavailable"
          description={error}
          action={{ label: "Retry", onClick: () => window.location.reload() }}
        />
      ) : loading || projectsLoading ? (
        <ActivityLoading />
      ) : activity.length === 0 ? (
        <StatePanel
          title="No activity recorded"
          description={
            projects.length === 0
              ? "Connect a project to begin building an audit history."
              : "Backend-recorded project and deployment events will appear here. ZeroOps does not add sample activity."
          }
          action={
            projects.length === 0
              ? { label: "Connect code", href: "/dashboard/repositories" }
              : undefined
          }
        />
      ) : (
        <section aria-labelledby="activity-timeline-heading" className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
          <div className="flex flex-col gap-1 border-b border-border px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <div>
              <h2 id="activity-timeline-heading" className="text-sm font-semibold text-foreground">
                Recorded events
              </h2>
              <p className="mt-1 text-xs text-foreground-muted">
                Ordered newest first from persisted workspace history.
              </p>
            </div>
            <span className="text-xs font-medium text-foreground-subtle tabular-nums">
              {activity.length} {activity.length === 1 ? "event" : "events"}
            </span>
          </div>
          <div className="px-4 py-1 sm:px-6">
          <ol>
            {activity.map((event, index) => {
              const Icon = iconForAction(event.action);
              return (
                <li key={event.id} className="relative flex gap-4 border-b border-border py-5 last:border-b-0">
                  {index < activity.length - 1 && (
                    <span aria-hidden="true" className="absolute bottom-0 left-[17px] top-12 w-px bg-border" />
                  )}
                  <span className="relative z-10 grid h-9 w-9 shrink-0 place-items-center rounded-full border border-border bg-surface-subtle text-primary">
                    <Icon size={16} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
                      <div>
                        <h3 className="text-sm font-semibold text-foreground">{event.action}</h3>
                        {event.project_name && (
                          <p className="mt-0.5 text-xs font-medium text-primary">{event.project_name}</p>
                        )}
                      </div>
                      <time
                        dateTime={event.created_at}
                        className="shrink-0 text-xs text-foreground-subtle"
                      >
                        {formatTimestamp(event.created_at)}
                      </time>
                    </div>
                    {event.details && (
                      <p className="mt-2 text-xs leading-5 text-foreground-muted">{event.details}</p>
                    )}
                    <p className="mt-2 text-xs font-medium text-foreground-subtle">
                      Persisted workspace event
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
          </div>
        </section>
      )}
    </div>
  );
}

function ActivityLoading() {
  return (
    <div role="status" className="flex min-h-56 items-center justify-center gap-2 rounded-xl border border-border bg-card text-sm text-foreground-muted">
      <Loader2 size={18} className="animate-spin text-primary motion-reduce:animate-none" aria-hidden="true" />
      Loading recorded activity…
    </div>
  );
}

function ActivityPageLoading() {
  return (
    <div className="pb-8">
      <PageHeader
        eyebrow="Audit history"
        title="Activity"
        description="A chronological record of events persisted by the backend."
      />
      <ActivityLoading />
    </div>
  );
}
