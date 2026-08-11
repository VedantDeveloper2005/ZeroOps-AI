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
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { MetricCard } from "@/components/ui/MetricCard";
import { StatePanel } from "@/components/ui/StatePanel";
import { StatusBadge } from "@/components/ui/StatusBadge";
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
  const [confirmation, setConfirmation] = useState<"deploy" | "delete" | null>(null);
  const [latestDetailState, setLatestDetailState] = useState<"idle" | "loading" | "ready" | "error">("idle");
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
        setLatestDetailState("loading");
        try {
          setLatestDetail(await api.getDeployment(projectDeployments[0].id));
          setLatestDetailState("ready");
        } catch {
          setLatestDetail(null);
          setLatestDetailState("error");
        }
      } else {
        setLatestDetail(null);
        setLatestDetailState("ready");
      }
    } catch (requestError) {
      setProject(null);
      setDeployments([]);
      setLatestDetail(null);
      setLatestDetailState("error");
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
    setConfirmation(null);
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
    setConfirmation(null);
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
      <div role="status" className="ops-surface flex min-h-[55vh] flex-col items-center justify-center px-6 text-center">
        <Loader2 size={22} className="animate-spin text-primary motion-reduce:animate-none" aria-hidden="true" />
        <h1 className="mt-4 text-lg font-semibold text-foreground">Loading project record</h1>
        <p className="mt-1 text-sm text-foreground-muted">Checking the project and its recorded releases.</p>
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
        headingLevel={1}
      />
    );
  }

  const latest = deployments[0] ?? null;
  const liveUrl = safeExternalUrl(latest?.live_url);
  const recentLogs = latestDetail?.logs.slice(-8) ?? [];

  return (
    <div className="mx-auto max-w-6xl space-y-7 pb-12">
      <Link
        href="/dashboard/projects"
        className="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-xs font-medium text-foreground-muted hover:bg-surface-subtle hover:text-foreground"
      >
        <ArrowLeft size={14} />
        Back to projects
      </Link>

      <header className="ops-surface relative flex flex-col gap-5 overflow-hidden p-5 sm:p-6 lg:flex-row lg:items-end lg:justify-between">
        <span aria-hidden="true" className="absolute inset-y-0 left-0 w-1 bg-primary" />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-semibold uppercase tracking-[0.1em] text-primary">Project</p>
            <StatusBadge status={latest?.status || "stopped"} label={latest?.status ? undefined : "No deployment recorded"} />
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
              className="ops-secondary"
            >
              <ExternalLink size={15} />
              Open recorded URL
            </a>
          )}
          <button
            type="button"
            onClick={() => void loadProject(true)}
            disabled={refreshing}
            className="ops-secondary disabled:opacity-50"
          >
            <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
          <button
            type="button"
            onClick={() => setConfirmation("deploy")}
            disabled={deploying || (latest ? activeStatuses.has(latest.status) : false)}
            className="ops-primary disabled:opacity-50"
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
          <MetricCard key={item.label} label={item.label} value={item.value} icon={item.icon} tone="info" />
        ))}
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
        <section className="ops-surface overflow-hidden">
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
                      <p className="mt-1 text-xs text-foreground-muted">
                        {formatTimestamp(deployment.started_at)}
                      </p>
                    </div>
                    <StatusBadge status={deployment.status} className="w-fit" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="ops-surface overflow-hidden">
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
          <div className="min-h-56 bg-[hsl(222_47%_7%)] p-4 font-mono text-xs leading-6 text-[hsl(210_40%_92%)]">
            {latestDetailState === "loading" ? (
              <p className="text-[hsl(215_18%_68%)]">Loading saved log records…</p>
            ) : latestDetailState === "error" ? (
              <p className="text-[hsl(38_92%_70%)]">Saved logs could not be verified for the latest deployment.</p>
            ) : recentLogs.length === 0 ? (
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

      <section className="ops-surface border-danger/25 p-5">
        <h2 className="text-sm font-semibold text-danger">Delete project record</h2>
        <p className="mt-2 max-w-3xl text-xs leading-5 text-foreground-muted">
          This removes the project and its linked ZeroOps records. It does not guarantee deletion of resources already created in your Azure account; review those resources separately.
        </p>
        <button
          type="button"
          onClick={() => setConfirmation("delete")}
          disabled={deleting}
          className="ops-danger mt-4 disabled:opacity-50"
        >
          {deleting ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
          Delete project
        </button>
      </section>

      <ConfirmDialog
        open={confirmation !== null}
        title={confirmation === "delete" ? "Delete this project record?" : "Start a production deployment?"}
        description={
          confirmation === "delete"
            ? `This permanently removes the ZeroOps record for ${project.name}. Azure resources already created may require separate cleanup.`
            : `This queues the saved ${project.branch || "default"} branch from ${project.full_name}. The workflow can create or update Azure resources and may incur charges.`
        }
        confirmLabel={confirmation === "delete" ? "Delete project record" : "Start deployment"}
        tone={confirmation === "delete" ? "danger" : "warning"}
        busy={confirmation === "delete" ? deleting : deploying}
        onClose={() => setConfirmation(null)}
        onConfirm={() => {
          if (confirmation === "delete") void deleteProject();
          if (confirmation === "deploy") void startDeployment();
        }}
      />
    </div>
  );
}
