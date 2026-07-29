"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  ExternalLink,
  FolderKanban,
  GitBranch,
  Plus,
  Search,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { useNotifications } from "@/lib/NotificationContext";
import { api, getErrorMessage, type Deployment } from "@/lib/api";

const activeStatuses = new Set(["queued", "building", "deploying"]);

function formatDate(value?: string | null) {
  if (!value) return "No deployment recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "No deployment recorded";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusPresentation(status?: string | null) {
  if (status === "running") {
    return { label: "Running", className: "border-success/25 bg-success-subtle text-success" };
  }
  if (activeStatuses.has(status || "")) {
    return { label: status || "In progress", className: "border-info/25 bg-info-subtle text-info" };
  }
  if (status === "failed") {
    return { label: "Failed", className: "border-danger/25 bg-danger-subtle text-danger" };
  }
  return { label: "Not deployed", className: "border-border bg-surface-subtle text-foreground-muted" };
}

export default function ProjectsPage() {
  const { projects, isLoading: projectsLoading } = useNotifications();
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  useEffect(() => {
    let cancelled = false;
    api.getDeployments(100)
      .then((data) => {
        if (!cancelled) setDeployments(data);
      })
      .catch((loadError) => {
        if (!cancelled) setError(getErrorMessage(loadError, "Deployment state could not be loaded."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const latestByProject = useMemo(() => {
    const latest = new Map<string, Deployment>();
    deployments.forEach((deployment) => {
      if (!latest.has(deployment.project_id)) latest.set(deployment.project_id, deployment);
    });
    return latest;
  }, [deployments]);

  const visibleProjects = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return projects.filter((project) => {
      const deployment = latestByProject.get(project.id);
      const status = deployment?.status || project.latest_deployment_status || project.status || "";
      const matchesQuery =
        !normalized ||
        project.name.toLowerCase().includes(normalized) ||
        project.full_name.toLowerCase().includes(normalized) ||
        project.framework.toLowerCase().includes(normalized);
      const matchesStatus =
        statusFilter === "all" ||
        (statusFilter === "active" && (status === "running" || activeStatuses.has(status))) ||
        (statusFilter === "failed" && status === "failed") ||
        (statusFilter === "not-deployed" && !deployment);
      return matchesQuery && matchesStatus;
    });
  }, [latestByProject, projects, query, statusFilter]);

  const isLoading = projectsLoading || loading;

  return (
    <div className="pb-8">
      <PageHeader
        eyebrow="Projects"
        title="Your application workspaces"
        description="Each project keeps source evidence, architecture decisions, deployments, logs, and production context together."
        actions={
          <Link href="/dashboard/repositories" className="ops-primary">
            <Plus size={16} />
            New project
          </Link>
        }
      />

      {error && (
        <StatePanel
          variant="error"
          title="Deployment state is unavailable"
          description={error}
          compact
          className="mb-5"
        />
      )}

      {isLoading ? (
        <div className="space-y-3" aria-busy="true" aria-label="Loading projects">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="skeleton h-28" />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <StatePanel
          title="No projects connected"
          description="Connect a GitHub repository or upload a ZIP archive to start a deployment-readiness review."
          action={{ label: "Connect code", href: "/dashboard/repositories" }}
        />
      ) : (
        <>
          <div className="mb-5 flex flex-col gap-3 rounded-xl border border-border bg-card p-3 shadow-sm sm:flex-row sm:items-center">
            <label className="relative min-w-0 flex-1">
              <span className="sr-only">Search projects</span>
              <Search
                aria-hidden="true"
                size={16}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-foreground-subtle"
              />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search name, repository, or framework"
                className="min-h-11 w-full rounded-lg border border-border bg-surface-subtle pl-9 pr-3 text-sm text-foreground outline-none placeholder:text-foreground-subtle focus:border-primary focus:ring-2 focus:ring-primary/15"
              />
            </label>
            <label className="sm:w-48">
              <span className="sr-only">Filter by deployment status</span>
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
                className="min-h-11 w-full rounded-lg border border-border bg-card px-3 text-sm text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
              >
                <option value="all">All statuses</option>
                <option value="active">Running or in progress</option>
                <option value="failed">Failed</option>
                <option value="not-deployed">Not deployed</option>
              </select>
            </label>
          </div>

          {visibleProjects.length === 0 ? (
            <StatePanel
              title="No projects match these filters"
              description="Clear the search or choose another status to see more projects."
              compact
            />
          ) : (
            <div className="grid gap-4 xl:grid-cols-2">
              {visibleProjects.map((project) => {
                const deployment = latestByProject.get(project.id);
                const status = statusPresentation(
                  deployment?.status || project.latest_deployment_status || project.status,
                );
                return (
                  <article key={project.id} className="rounded-xl border border-border bg-card p-5 shadow-sm">
                    <div className="flex items-start gap-3">
                      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-primary-subtle text-primary">
                        <FolderKanban size={18} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h2 className="truncate text-sm font-semibold text-foreground">{project.name}</h2>
                          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold capitalize ${status.className}`}>
                            {status.label}
                          </span>
                        </div>
                        <p className="mt-1 truncate text-xs text-foreground-muted">
                          {project.full_name.startsWith("upload/") ? "Uploaded archive" : project.full_name}
                        </p>
                      </div>
                    </div>

                    <dl className="mt-5 grid grid-cols-2 gap-4 border-y border-border py-4 text-xs sm:grid-cols-4">
                      <div>
                        <dt className="text-foreground-subtle">Framework</dt>
                        <dd className="mt-1 truncate font-medium text-foreground">{project.framework || "Unknown"}</dd>
                      </div>
                      <div>
                        <dt className="text-foreground-subtle">Branch</dt>
                        <dd className="mt-1 flex items-center gap-1 truncate font-mono text-[11px] font-medium text-foreground">
                          <GitBranch size={12} /> {project.branch || "Not recorded"}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-foreground-subtle">Region</dt>
                        <dd className="mt-1 truncate font-medium text-foreground">{project.region || "Not selected"}</dd>
                      </div>
                      <div>
                        <dt className="text-foreground-subtle">Deployments</dt>
                        <dd className="mt-1 font-medium text-foreground tabular-nums">{project.deployment_count}</dd>
                      </div>
                    </dl>

                    <p className="mt-4 text-[11px] text-foreground-subtle">
                      Last deployment: {formatDate(deployment?.completed_at || deployment?.started_at || project.last_deployed_at)}
                    </p>
                    <div className="mt-4 flex flex-wrap justify-end gap-2">
                      {deployment?.live_url && (
                        <a
                          href={deployment.live_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-border px-3 text-xs font-medium text-foreground-muted transition-colors hover:bg-surface-raised hover:text-foreground"
                        >
                          Open URL <ExternalLink size={13} />
                        </a>
                      )}
                      <Link
                        href={`/dashboard/apps/${project.id}`}
                        className="inline-flex min-h-10 items-center gap-1.5 rounded-lg bg-primary px-3 text-xs font-semibold text-white transition-colors hover:bg-primary-hover"
                      >
                        Open project <ArrowRight size={13} />
                      </Link>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
