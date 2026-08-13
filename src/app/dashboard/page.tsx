"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  ExternalLink,
  FolderKanban,
  GitPullRequestArrow,
  Loader2,
  Plus,
  Rocket,
  ShieldAlert,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { MetricCard } from "@/components/ui/MetricCard";
import { StatePanel } from "@/components/ui/StatePanel";
import { useAuth } from "@/lib/AuthContext";
import { useNotifications } from "@/lib/NotificationContext";
import {
  api,
  getErrorMessage,
  type Deployment,
  type InfrastructurePlan,
} from "@/lib/api";

const activeStatuses = new Set(["queued", "building", "deploying"]);
const successfulStatuses = new Set(["running"]);

function formatDate(value?: string | null) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not recorded";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function safeExternalUrl(value?: string | null) {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:"
      ? parsed.toString()
      : null;
  } catch {
    return null;
  }
}

function projectState(status?: string | null) {
  if (successfulStatuses.has(status || "")) {
    return {
      label: "Deployment running",
      className: "border-success/25 bg-success-subtle text-success",
    };
  }
  if (activeStatuses.has(status || "")) {
    return { label: "In progress", className: "border-info/25 bg-info-subtle text-info" };
  }
  if (status === "failed" || status === "error") {
    return { label: "Needs attention", className: "border-danger/25 bg-danger-subtle text-danger" };
  }
  return { label: "Not deployed", className: "border-border bg-surface-subtle text-foreground-muted" };
}

export default function DashboardHome() {
  const { user } = useAuth();
  const {
    projects,
    dashboardStats,
    notifications,
    isLoading: workspaceLoading,
  } = useNotifications();
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [draftPlanProjectIds, setDraftPlanProjectIds] = useState<Set<string>>(new Set());
  const [unknownPlanProjectIds, setUnknownPlanProjectIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadOverview() {
      setLoading(true);
      setError(null);
      setUnknownPlanProjectIds(new Set());
      try {
        const deploymentData = await api.getDeployments(50);
        if (cancelled) return;
        setDeployments(deploymentData);

        const planResults = await Promise.allSettled(
          projects.map((project) => api.getInfrastructurePlan(project.id)),
        );
        if (cancelled) return;
        const awaitingApproval = new Set<string>();
        const unavailablePlans = new Set<string>();
        planResults.forEach((result, index) => {
          if (
            result.status === "fulfilled" &&
            (result.value as InfrastructurePlan).status === "draft"
          ) {
            awaitingApproval.add(projects[index].id);
          } else if (result.status === "rejected") {
            unavailablePlans.add(projects[index].id);
          }
        });
        setDraftPlanProjectIds(awaitingApproval);
        setUnknownPlanProjectIds(unavailablePlans);
      } catch (loadError) {
        if (!cancelled) {
          setError(getErrorMessage(loadError, "The workspace overview could not be loaded."));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    if (!workspaceLoading) void loadOverview();
    return () => {
      cancelled = true;
    };
  }, [projects, workspaceLoading]);

  const latestByProject = useMemo(() => {
    const records = new Map<string, Deployment>();
    deployments.forEach((deployment) => {
      if (!records.has(deployment.project_id)) records.set(deployment.project_id, deployment);
    });
    return records;
  }, [deployments]);

  const activeDeployments = deployments.filter((deployment) => activeStatuses.has(deployment.status));
  const failedDeployments = Array.from(latestByProject.values()).filter(
    (deployment) => deployment.status === "failed",
  );
  const incidentNotifications = notifications.filter((notification) => notification.category === "incident");
  const criticalNotifications = notifications.filter(
    (notification) => !notification.read && notification.type === "critical",
  );
  const firstName = user?.first_name || user?.firstName || "there";

  const attentionItems = [
    ...Array.from(draftPlanProjectIds).map((projectId) => {
      const project = projects.find((item) => item.id === projectId);
      return {
        id: `plan-${projectId}`,
        icon: GitPullRequestArrow,
        tone: "warning",
        title: `${project?.name || "Project"} architecture is awaiting approval`,
        description: "Review the resource plan, estimate status, and preflight evidence before deployment.",
        href: `/dashboard/infrastructure?project=${projectId}`,
        action: "Review plan",
      };
    }),
    ...Array.from(unknownPlanProjectIds).map((projectId) => {
      const project = projects.find((item) => item.id === projectId);
      return {
        id: `plan-unavailable-${projectId}`,
        icon: AlertCircle,
        tone: "warning",
        title: `${project?.name || "Project"} plan status is unavailable`,
        description:
          "ZeroOps could not read the saved plan, so no approval or readiness state is being assumed.",
        href: `/dashboard/infrastructure?project=${projectId}`,
        action: "Check plan",
      };
    }),
    ...failedDeployments.slice(0, 3).map((deployment) => ({
      id: `deployment-${deployment.id}`,
      icon: AlertCircle,
      tone: "danger",
      title: `${deployment.project_name || "Deployment"} failed`,
      description: "Open the recorded stages and logs before deciding whether to retry.",
      href: `/dashboard/deployments?id=${deployment.id}`,
      action: "View failure",
    })),
    ...criticalNotifications.slice(0, 2).map((notification) => ({
      id: `notification-${notification.id}`,
      icon: ShieldAlert,
      tone: "danger",
      title: notification.title,
      description: notification.message,
      href: notification.action_url || "/dashboard/activity",
      action: "Review",
    })),
  ];

  if (workspaceLoading || loading) {
    return (
      <div className="space-y-6" aria-busy="true" aria-label="Loading workspace overview">
        <div className="skeleton h-28 w-full" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="skeleton h-32" />
          ))}
        </div>
        <div className="skeleton h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="pb-8">
      <PageHeader
        eyebrow="Workspace overview"
        title={`Good to see you, ${firstName}.`}
        description="Start with decisions that need your attention, then check active releases and production context."
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
          title="Overview data is temporarily unavailable"
          description={error}
          action={{ label: "Retry", onClick: () => window.location.reload() }}
          compact
          className="mb-6"
        />
      )}

      {projects.length === 0 ? (
        <StatePanel
          title="Connect your first codebase"
          description="Connect GitHub or upload a ZIP archive. ZeroOps will record the source, analyze deployment requirements, and prepare a reviewable Azure App Service plan."
          action={{ label: "Connect code", href: "/dashboard/repositories" }}
          className="mb-8"
        />
      ) : (
        <>
          <section aria-labelledby="attention-heading" className="mb-8">
            <div className="mb-4 flex items-end justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.1em] text-primary">
                  Decision queue
                </p>
                <h2 id="attention-heading" className="mt-1 text-lg font-semibold tracking-tight text-foreground">
                  What needs you now
                </h2>
                <p className="mt-1 text-xs text-foreground-muted">
                  Approval, recovery, and unreadable plan states stay visible until they can be reviewed.
                </p>
              </div>
              {attentionItems.length > 0 && (
                <span className="text-xs font-medium text-foreground-subtle">{attentionItems.length} open</span>
              )}
            </div>
            {attentionItems.length === 0 ? (
              <div className="flex items-center gap-3 rounded-xl border border-success/25 bg-success-subtle px-4 py-5">
                <CheckCircle2 size={19} className="shrink-0 text-success" />
                <div>
                  <p className="text-sm font-medium text-foreground">No recorded actions in this view</p>
                  <p className="mt-0.5 text-xs text-foreground-muted">
                    No failed releases, pending plan approvals, or critical notifications were returned. This is not a health signal.
                  </p>
                </div>
              </div>
            ) : (
              <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card shadow-sm">
                {attentionItems.map((item) => {
                  const Icon = item.icon;
                  return (
                    <article key={item.id} className="flex flex-col gap-4 p-4 transition-colors hover:bg-surface-subtle sm:flex-row sm:items-center sm:p-5">
                      <span
                        className={`grid h-10 w-10 shrink-0 place-items-center rounded-lg ${
                          item.tone === "danger"
                            ? "bg-danger-subtle text-danger"
                            : "bg-warning-subtle text-warning"
                        }`}
                      >
                        <Icon size={18} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <h3 className="text-sm font-semibold text-foreground">{item.title}</h3>
                        <p className="mt-1 text-xs leading-5 text-foreground-muted">{item.description}</p>
                      </div>
                      <Link
                        href={item.href}
                        className="inline-flex min-h-10 shrink-0 items-center justify-center gap-1.5 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground transition-colors hover:bg-surface-raised"
                      >
                        {item.action} <ArrowRight size={13} />
                      </Link>
                    </article>
                  );
                })}
              </div>
            )}
          </section>

          {activeDeployments.length > 0 && (
            <section aria-labelledby="active-deployments-heading" className="mb-8 rounded-xl border border-border bg-card p-4 shadow-sm sm:p-5">
              <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                <div>
                <p className="text-xs font-semibold uppercase tracking-[0.1em] text-info">Live queue state</p>
                <h2 id="active-deployments-heading" className="mt-1 text-lg font-semibold tracking-tight text-foreground">
                  Active deployments
                </h2>
                <p className="mt-1 text-xs text-foreground-muted">Current state reported by the deployment queue.</p>
                </div>
                <Link href="/dashboard/deployments" className="text-xs font-semibold text-primary hover:text-primary-hover">
                  Open deployment center
                </Link>
              </div>
              <div className="grid gap-3 lg:grid-cols-2">
                {activeDeployments.slice(0, 4).map((deployment) => (
                  <Link
                    key={deployment.id}
                    href={`/dashboard/deployments?id=${deployment.id}`}
                    className="group rounded-lg border border-info/25 bg-surface-subtle p-4 transition-colors hover:border-info/50 hover:bg-card"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-foreground">
                          {deployment.project_name || "Deployment"}
                        </p>
                        <p className="mt-1 text-xs text-foreground-muted">
                          {deployment.environment} · {deployment.branch}
                        </p>
                      </div>
                      <span className="inline-flex items-center gap-1.5 rounded-full border border-info/25 bg-info-subtle px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-info">
                        <Loader2 size={11} className="animate-spin motion-reduce:animate-none" />
                        {deployment.status}
                      </span>
                    </div>
                    <p className="mt-4 text-xs text-foreground-subtle">
                      Waiting for the deployment worker to report the next durable status.
                    </p>
                    <p className="mt-2 flex items-center gap-1.5 text-[11px] text-foreground-subtle">
                      <Clock3 size={12} /> Started {formatDate(deployment.started_at)}
                    </p>
                  </Link>
                ))}
              </div>
            </section>
          )}

          <section aria-labelledby="health-summary-heading" className="mb-8">
            <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
              <p className="text-xs font-semibold uppercase tracking-[0.1em] text-primary">Workspace pulse</p>
              <h2 id="health-summary-heading" className="mt-1 text-lg font-semibold tracking-tight text-foreground">
                Recorded operational state
              </h2>
              <p className="mt-1 text-xs text-foreground-muted">
                Recorded workspace state—not inferred uptime or security guarantees.
              </p>
              </div>
              <Link href="/dashboard/activity" className="inline-flex min-h-10 items-center gap-1.5 text-xs font-semibold text-primary hover:text-primary-hover">
                Review audit history <ArrowRight size={13} aria-hidden="true" />
              </Link>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Connected projects"
                value={String(projects.length)}
                supportingText="GitHub repositories and uploaded archives"
                icon={FolderKanban}
                tone="info"
              />
              <MetricCard
                label="Active deployments"
                value={String(activeDeployments.length)}
                supportingText="Queued, building, or deploying"
                icon={Rocket}
                tone={activeDeployments.length > 0 ? "info" : "neutral"}
              />
              <MetricCard
                label="Failed deployments"
                value={String(dashboardStats?.failed_deployments ?? failedDeployments.length)}
                supportingText="Recorded release failures"
                icon={AlertCircle}
                tone={(dashboardStats?.failed_deployments ?? failedDeployments.length) > 0 ? "danger" : "neutral"}
              />
              <MetricCard
                label="Incident notifications"
                value={String(incidentNotifications.length)}
                supportingText="Notification records; read state is not resolution"
                icon={ShieldAlert}
                tone={incidentNotifications.length > 0 ? "warning" : "neutral"}
              />
            </div>
          </section>

          <section aria-labelledby="projects-heading">
            <div className="mb-3 flex items-end justify-between gap-4">
              <div>
                <h2 id="projects-heading" className="text-base font-semibold text-foreground">Projects</h2>
                <p className="mt-1 text-xs text-foreground-muted">Latest recorded release state for each codebase.</p>
              </div>
              <Link href="/dashboard/projects" className="text-xs font-semibold text-primary hover:text-primary-hover">
                View all
              </Link>
            </div>
            <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
              {projects.slice(0, 6).map((project) => {
                const deployment = latestByProject.get(project.id);
                const state = projectState(
                  deployment?.status || project.latest_deployment_status,
                );
                const liveUrl = safeExternalUrl(deployment?.live_url);
                return (
                  <article
                    key={project.id}
                    className="flex flex-col gap-4 border-b border-border p-4 last:border-b-0 sm:flex-row sm:items-center"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="truncate text-sm font-semibold text-foreground">{project.name}</h3>
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${state.className}`}>
                          {state.label}
                        </span>
                      </div>
                      <p className="mt-1 truncate text-xs text-foreground-muted">
                        {project.full_name.startsWith("upload/") ? "Uploaded archive" : project.full_name}
                      </p>
                      <p className="mt-2 text-[11px] text-foreground-subtle">
                        {project.branch || "No branch recorded"} · {project.region || "No region selected"} · Last release{" "}
                        {formatDate(deployment?.completed_at || deployment?.started_at || project.last_deployed_at)}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {liveUrl && (
                        <a
                          href={liveUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-border px-3 text-xs font-medium text-foreground-muted transition-colors hover:bg-surface-raised hover:text-foreground"
                        >
                          Open URL <ExternalLink size={13} />
                        </a>
                      )}
                      <Link
                        href={`/dashboard/apps/${project.id}`}
                        className="inline-flex min-h-10 items-center gap-1.5 rounded-lg bg-surface-subtle px-3 text-xs font-semibold text-foreground transition-colors hover:bg-surface-raised"
                      >
                        Open project <ArrowRight size={13} />
                      </Link>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
