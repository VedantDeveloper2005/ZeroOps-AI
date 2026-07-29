"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Clock3,
  ExternalLink,
  FileText,
  GitBranch,
  Loader2,
  MapPin,
  RefreshCw,
  Rocket,
  Trash2,
} from "lucide-react";
import { ProjectTabs } from "@/components/dashboard/ProjectTabs";
import { StatePanel } from "@/components/ui/StatePanel";
import { useNotifications } from "@/lib/NotificationContext";
import {
  api,
  getErrorMessage,
  type Deployment,
  type DeploymentDetail,
  type Project,
} from "@/lib/api";

const activeStatuses = new Set<Deployment["status"]>(["queued", "building", "deploying"]);

function formatTimestamp(value: string | null) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not recorded";
  return date.toLocaleString();
}

function safeExternalUrl(value: string | null | undefined) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

function statusClass(status: Deployment["status"] | null) {
  if (status === "running") return "border-success/25 bg-success-subtle text-success";
  if (status === "failed" || status === "stopped") return "border-danger/25 bg-danger-subtle text-danger";
  if (status && activeStatuses.has(status)) return "border-info/25 bg-info-subtle text-info";
  return "border-border bg-surface-subtle text-foreground-muted";
}

export default function AppDetailsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { addToast, refreshProjects, refreshStats } = useNotifications();
  const projectId = params.id;
  const [project, setProject] = useState<Project | null>(null);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [latestDetail, setLatestDetail] = useState<DeploymentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadProject = useCallback(async (background = false) => {
    if (!projectId) return;
    if (background) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const [projectResult, deploymentResult] = await Promise.all([
        api.getProject(projectId),
        api.getDeployments(100),
      ]);
      const projectDeployments = deploymentResult
        .filter((deployment) => deployment.project_id === projectId)
        .sort((left, right) => {
          const leftTime = new Date(left.started_at || 0).getTime();
          const rightTime = new Date(right.started_at || 0).getTime();
          return rightTime - leftTime;
        });

      setProject(projectResult);
      setDeployments(projectDeployments);
      if (projectDeployments[0]) {
        try {
          setLatestDetail(await api.getDeployment(projectDeployments[0].id));
        } catch {
          setLatestDetail(null);
        }
      } else {
        setLatestDetail(null);
      }
    } catch (requestError) {
      setProject(null);
      setDeployments([]);
      setLatestDetail(null);
      setError(getErrorMessage(requestError, "Project details could not be loaded."));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [projectId]);

  useEffect(() => {
    void loadProject();
  }, [loadProject]);

  const startDeployment = async () => {
    if (!project || deploying) return;
    const confirmed = window.confirm(
      `Start a deployment from ${project.full_name} on branch ${project.branch || "the saved default"}? This can create or update Azure resources and may incur charges.`,
    );
    if (!confirmed) return;

    setDeploying(true);
    try {
      const result = await api.startDeployment({
        project_id: project.id,
        branch: project.branch,
        environment: "production",
      });
      await Promise.all([refreshProjects(), refreshStats()]);
      addToast("Deployment workflow started from the saved project branch.", "success");
      router.push(`/dashboard/deployments?id=${result.deployment_id}`);
    } catch (requestError) {
      addToast(getErrorMessage(requestError, "The deployment could not be started."), "error");
    } finally {
      setDeploying(false);
    }
  };

  const deleteProject = async () => {
    if (!project || deleting) return;
    const confirmed = window.confirm(
      `Delete the ZeroOps project record for “${project.name}”? This cannot be undone. External Azure resources may require separate cleanup.`,
    );
    if (!confirmed) return;

    setDeleting(true);
    try {
      await api.deleteProject(project.id);
      await Promise.all([refreshProjects(), refreshStats()]);
      addToast("Project record deleted.", "success");
      router.push("/dashboard/projects");
    } catch (requestError) {
      addToast(getErrorMessage(requestError, "The project could not be deleted."), "error");
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div role="status" className="flex min-h-[55vh] items-center justify-center gap-3 rounded-xl border border-border bg-card text-sm text-foreground-muted">
        <Loader2 size={18} className="animate-spin text-primary" />
        Loading project record…
      </div>
    );
  }

  if (error || !project) {
    return (
      <StatePanel
        variant="error"
        title="Project is unavailable"
        description={error || "This project could not be found or you do not have access to it."}
        action={{ label: "Back to projects", href: "/dashboard/projects" }}
      />
    );
  }

  const latest = deployments[0] ?? null;
  const liveUrl = safeExternalUrl(latest?.live_url);
  const recentLogs = latestDetail?.logs.slice(-8) ?? [];

  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-12">
      <Link
        href="/dashboard/projects"
        className="inline-flex min-h-10 items-center gap-1.5 text-xs font-medium text-foreground-muted hover:text-foreground"
      >
        <ArrowLeft size={14} />
        Back to projects
      </Link>

      <header className="flex flex-col gap-5 border-b border-border pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-semibold uppercase tracking-[0.1em] text-primary">Project</p>
            <span className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide ${statusClass(latest?.status ?? null)}`}>
              {latest?.status ? latest.status.replaceAll("_", " ") : "Not deployed"}
            </span>
          </div>
          <h1 className="mt-2 truncate text-2xl font-semibold tracking-[-0.035em] text-foreground sm:text-[2rem]">
            {project.name}
          </h1>
          <p className="mt-1 break-all text-sm text-foreground-muted">{project.full_name}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {liveUrl && (
            <a
              href={liveUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground shadow-sm hover:bg-surface-raised"
            >
              <ExternalLink size={15} />
              Open recorded URL
            </a>
          )}
          <button
            type="button"
            onClick={() => void loadProject(true)}
            disabled={refreshing}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground shadow-sm hover:bg-surface-raised disabled:opacity-50"
          >
            <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
          <button
            type="button"
            onClick={() => void startDeployment()}
            disabled={deploying || (latest ? activeStatuses.has(latest.status) : false)}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-primary px-4 text-xs font-semibold text-white shadow-sm hover:bg-primary-hover disabled:opacity-50"
          >
            {deploying ? <Loader2 size={15} className="animate-spin" /> : <Rocket size={15} />}
            {latest && activeStatuses.has(latest.status) ? "Deployment active" : "Start deployment"}
          </button>
        </div>
      </header>

      <ProjectTabs projectId={project.id} />

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: "Source branch", value: project.branch || "Not recorded", icon: GitBranch },
          { label: "Framework", value: project.framework || "Not detected", icon: FileText },
          { label: "Region", value: project.region || "Not recorded", icon: MapPin },
          { label: "Last deployment", value: formatTimestamp(project.last_deployed_at), icon: Clock3 },
        ].map((item) => (
          <div key={item.label} className="rounded-xl border border-border bg-card p-4 shadow-sm">
            <item.icon size={16} className="text-primary" />
            <p className="mt-3 text-xs font-medium text-foreground-muted">{item.label}</p>
            <p className="mt-1 break-words text-sm font-semibold text-foreground">{item.value}</p>
          </div>
        ))}
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
        <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-4 sm:px-5">
            <div>
              <h2 className="text-sm font-semibold text-foreground">Recent deployments</h2>
              <p className="mt-1 text-xs text-foreground-muted">Durable deployment records for this project.</p>
            </div>
            <Link href={`/dashboard/deployments?project=${project.id}`} className="text-xs font-semibold text-primary hover:underline">
              View all
            </Link>
          </div>
          {deployments.length === 0 ? (
            <div className="px-5 py-10 text-center">
              <p className="text-sm font-semibold text-foreground">No deployments recorded</p>
              <p className="mt-1 text-xs text-foreground-muted">Approve an architecture plan before starting the first deployment.</p>
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {deployments.slice(0, 6).map((deployment) => (
                <li key={deployment.id}>
                  <Link
                    href={`/dashboard/deployments?id=${deployment.id}`}
                    className="grid gap-2 px-4 py-3 hover:bg-surface-subtle sm:grid-cols-[1fr_auto] sm:items-center sm:px-5"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-xs font-semibold text-foreground">
                        {deployment.branch || "Default branch"} · {deployment.environment}
                      </p>
                      <p className="mt-1 text-[11px] text-foreground-muted">
                        {formatTimestamp(deployment.started_at)}
                      </p>
                    </div>
                    <span className={`w-fit rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${statusClass(deployment.status)}`}>
                      {deployment.status.replaceAll("_", " ")}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-4 sm:px-5">
            <div>
              <h2 className="text-sm font-semibold text-foreground">Latest saved logs</h2>
              <p className="mt-1 text-xs text-foreground-muted">Persisted entries from the latest deployment.</p>
            </div>
            {latest && (
              <Link href={`/dashboard/logs?project=${project.id}&deployment=${latest.id}`} className="text-xs font-semibold text-primary hover:underline">
                Open logs
              </Link>
            )}
          </div>
          <div className="min-h-56 bg-[hsl(222_47%_7%)] p-4 font-mono text-[11px] leading-6 text-[hsl(210_40%_92%)]">
            {recentLogs.length === 0 ? (
              <p className="text-[hsl(215_18%_68%)]">No log entries are saved for the latest deployment.</p>
            ) : (
              recentLogs.map((log, index) => (
                <div key={`${log.line_number}-${index}`} className="grid gap-2 sm:grid-cols-[56px_1fr]">
                  <span className={log.level === "ERROR" ? "text-[hsl(0_84%_68%)]" : log.level === "WARN" ? "text-[hsl(38_92%_61%)]" : "text-[hsl(199_89%_63%)]"}>
                    {log.level}
                  </span>
                  <span className="break-words">{log.message}</span>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      <section className="rounded-xl border border-danger/25 bg-card p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-danger">Delete project record</h2>
        <p className="mt-2 max-w-3xl text-xs leading-5 text-foreground-muted">
          This removes the project and its linked ZeroOps records. It does not guarantee deletion of resources already created in your Azure account; review those resources separately.
        </p>
        <button
          type="button"
          onClick={() => void deleteProject()}
          disabled={deleting}
          className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-lg bg-danger px-4 text-xs font-semibold text-white hover:bg-danger-hover disabled:opacity-50"
        >
          {deleting ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
          Delete project
        </button>
      </section>
    </div>
  );
}
