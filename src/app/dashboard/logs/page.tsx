"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { FileText, Loader2, RefreshCw, Search } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { ProjectSelector } from "@/components/dashboard/ProjectSelector";
import { ProjectTabs } from "@/components/dashboard/ProjectTabs";
import { useNotifications } from "@/lib/NotificationContext";
import {
  api,
  getErrorMessage,
  type Deployment,
  type DeploymentDetail,
  type DeploymentLog,
} from "@/lib/api";
import { createReconnectingWebSocket } from "@/lib/runtime-config";

type LevelFilter = "info" | "warning" | "error" | "debug";
type StreamState = "idle" | "connecting" | "connected" | "reconnecting" | "complete" | "unavailable";

const filters: LevelFilter[] = ["info", "warning", "error", "debug"];
const activeStatuses = new Set<Deployment["status"]>(["queued", "building", "deploying"]);

function normalizeLevel(level: string): LevelFilter {
  const normalized = level.toLowerCase();
  if (normalized === "warn" || normalized === "warning") return "warning";
  if (normalized === "error") return "error";
  if (normalized === "debug") return "debug";
  return "info";
}

function logKey(log: DeploymentLog) {
  return `${log.line_number}:${log.timestamp ?? ""}:${log.message}`;
}

function formatDeployment(deployment: Deployment) {
  const started = deployment.started_at
    ? new Date(deployment.started_at).toLocaleString()
    : "time not recorded";
  return `${deployment.branch || "default branch"} · ${deployment.status} · ${started}`;
}

export default function LogsPage() {
  return (
    <Suspense fallback={<LogsPageLoading />}>
      <LogsWorkspace />
    </Suspense>
  );
}

function LogsWorkspace() {
  const searchParams = useSearchParams();
  const { projects, isLoading: projectsLoading } = useNotifications();
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedDeploymentId, setSelectedDeploymentId] = useState("");
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [detail, setDetail] = useState<DeploymentDetail | null>(null);
  const [logs, setLogs] = useState<DeploymentLog[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [activeLevels, setActiveLevels] = useState<Set<LevelFilter>>(new Set(filters));
  const [streamState, setStreamState] = useState<StreamState>("idle");
  const shouldStream = detail ? activeStatuses.has(detail.status) : false;

  useEffect(() => {
    const requestedProject = searchParams.get("project");
    if (requestedProject && projects.some((project) => project.id === requestedProject)) {
      setSelectedProjectId(requestedProject);
      return;
    }
    if (!selectedProjectId && projects.length > 0) setSelectedProjectId(projects[0].id);
  }, [projects, searchParams, selectedProjectId]);

  const loadDeployments = useCallback(async (projectId: string) => {
    if (!projectId) return;
    setLoadingHistory(true);
    setError(null);
    try {
      const projectDeployments = (await api.getDeployments(100)).filter(
        (deployment) => deployment.project_id === projectId,
      );
      setDeployments(projectDeployments);
      setSelectedDeploymentId((current) => {
        const requested = searchParams.get("deployment");
        if (requested && projectDeployments.some((deployment) => deployment.id === requested)) {
          return requested;
        }
        if (projectDeployments.some((deployment) => deployment.id === current)) return current;
        return projectDeployments[0]?.id ?? "";
      });
    } catch (requestError) {
      setDeployments([]);
      setSelectedDeploymentId("");
      setError(getErrorMessage(requestError, "Deployment history could not be loaded."));
    } finally {
      setLoadingHistory(false);
    }
  }, [searchParams]);

  useEffect(() => {
    void loadDeployments(selectedProjectId);
  }, [loadDeployments, selectedProjectId]);

  const loadDetail = useCallback(async (deploymentId: string) => {
    if (!deploymentId) {
      setDetail(null);
      setLogs([]);
      setStreamState("idle");
      return;
    }
    setLoadingDetail(true);
    setError(null);
    try {
      const nextDetail = await api.getDeployment(deploymentId);
      setDetail(nextDetail);
      setLogs(nextDetail.logs ?? []);
      setStreamState(activeStatuses.has(nextDetail.status) ? "connecting" : "complete");
    } catch (requestError) {
      setDetail(null);
      setLogs([]);
      setStreamState("unavailable");
      setError(getErrorMessage(requestError, "Deployment logs could not be loaded."));
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    void loadDetail(selectedDeploymentId);
  }, [loadDetail, selectedDeploymentId]);

  useEffect(() => {
    if (!selectedDeploymentId || !shouldStream) return;

    let active = true;
    const dispose = createReconnectingWebSocket(`/ws/deployments/${selectedDeploymentId}`, {
      onOpen: () => {
        if (active) setStreamState("connected");
      },
      onMessage: (event) => {
        if (!active) return;
        try {
          const data = JSON.parse(event.data) as Record<string, unknown>;
          if (data.type === "log" && typeof data.text === "string") {
            const nextLog: DeploymentLog = {
              line_number: typeof data.line_number === "number" ? data.line_number : 0,
              level:
                normalizeLevel(typeof data.lineType === "string" ? data.lineType : "info") === "warning"
                  ? "WARN"
                  : normalizeLevel(typeof data.lineType === "string" ? data.lineType : "info").toUpperCase() as DeploymentLog["level"],
              message: data.text,
              timestamp: typeof data.timestamp === "string" ? data.timestamp : null,
            };
            setLogs((current) => {
              const key = logKey(nextLog);
              return current.some((log) => logKey(log) === key) ? current : [...current, nextLog];
            });
          }
          if (data.type === "status" && typeof data.status === "string") {
            const nextStatus = data.status as Deployment["status"];
            setDetail((current) => current ? { ...current, status: nextStatus } : current);
            if (!activeStatuses.has(nextStatus)) {
              setStreamState("complete");
              void loadDetail(selectedDeploymentId);
            }
          }
        } catch {
          setStreamState("reconnecting");
        }
      },
      onError: () => {
        if (active) setStreamState("reconnecting");
      },
      onClose: () => {
        if (active) setStreamState("unavailable");
      },
    });

    return () => {
      active = false;
      dispose();
    };
  }, [loadDetail, selectedDeploymentId, shouldStream]);

  const filteredLogs = useMemo(() => {
    const term = search.trim().toLowerCase();
    return logs.filter((log) => {
      const level = normalizeLevel(log.level);
      return activeLevels.has(level) && (!term || log.message.toLowerCase().includes(term));
    });
  }, [activeLevels, logs, search]);

  const toggleLevel = (level: LevelFilter) => {
    setActiveLevels((current) => {
      const next = new Set(current);
      if (next.has(level)) next.delete(level);
      else next.add(level);
      return next;
    });
  };

  if (projectsLoading) return <LogsPageLoading />;

  if (projects.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Diagnostics"
          title="Deployment logs"
          description="Persisted worker output is shown only for recorded deployment runs."
        />
        <StatePanel
          title="No deployment logs"
          description="Connect a project and start a deployment before reviewing build and runtime output."
          action={{ label: "Connect a project", href: "/dashboard/repositories" }}
        />
      </div>
    );
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const busy = loadingHistory || loadingDetail;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Diagnostics"
        title="Deployment logs"
        description="Persisted worker output for a specific deployment. Active deployments stream new database-backed entries; completed deployments show their saved history."
        actions={
          <button
            type="button"
            onClick={() => void loadDetail(selectedDeploymentId)}
            disabled={busy || !selectedDeploymentId}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground shadow-sm hover:bg-surface-raised disabled:opacity-50"
          >
            <RefreshCw size={15} className={busy ? "animate-spin" : ""} />
            Refresh
          </button>
        }
      />

      <section aria-label="Log context" className="rounded-xl border border-border bg-card p-4 shadow-sm sm:p-5">
        <div className="grid gap-4 md:grid-cols-2">
          <ProjectSelector projects={projects} value={selectedProjectId} onChange={setSelectedProjectId} />
          <label>
            <span className="mb-1.5 block text-xs font-medium text-foreground-muted">Deployment</span>
            <select
              value={selectedDeploymentId}
              onChange={(event) => setSelectedDeploymentId(event.target.value)}
              disabled={deployments.length === 0}
              className="min-h-11 w-full rounded-lg border border-border bg-surface-subtle px-3 text-sm font-medium text-foreground outline-none transition-colors focus:border-primary focus:bg-card focus:ring-2 focus:ring-primary/15 disabled:opacity-60"
            >
              {deployments.length === 0 ? (
                <option value="">No deployments recorded</option>
              ) : (
                deployments.map((deployment) => (
                  <option key={deployment.id} value={deployment.id}>
                    {formatDeployment(deployment)}
                  </option>
                ))
              )}
            </select>
          </label>
        </div>

        {selectedProject && (
          <div className="mt-5">
            <ProjectTabs projectId={selectedProject.id} />
          </div>
        )}
      </section>

      {error ? (
        <StatePanel
          variant="error"
          title="Logs are unavailable"
          description={error}
          action={{ label: "Try again", onClick: () => void loadDetail(selectedDeploymentId) }}
        />
      ) : busy ? (
        <LogsLoading compact />
      ) : deployments.length === 0 ? (
        <StatePanel
          title="No deployments recorded"
          description="Logs are stored against deployment records. Start a deployment to create the first log stream."
          action={{ label: "Open deployments", href: "/dashboard/deployments" }}
        />
      ) : (
        <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
          <div className="flex flex-col gap-3 border-b border-border p-4 lg:flex-row lg:items-center lg:justify-between">
            <label className="flex min-h-11 flex-1 items-center gap-2 rounded-lg border border-border bg-surface-subtle px-3">
              <Search size={15} className="text-foreground-muted" aria-hidden="true" />
              <span className="sr-only">Search deployment logs</span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search saved log messages"
                className="w-full bg-transparent text-xs text-foreground outline-none placeholder:text-foreground-subtle"
              />
            </label>
            <div className="flex flex-wrap gap-1.5" aria-label="Log level filters">
              {filters.map((level) => (
                <button
                  key={level}
                  type="button"
                  aria-pressed={activeLevels.has(level)}
                  onClick={() => toggleLevel(level)}
                  className={`min-h-11 rounded-lg border px-3 text-xs font-semibold capitalize transition-colors ${
                    activeLevels.has(level)
                      ? "border-primary/25 bg-primary-subtle text-primary"
                      : "border-border bg-card text-foreground-muted"
                  }`}
                >
                  {level}
                </button>
              ))}
            </div>
          </div>

          <div
            aria-live="polite"
            className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-surface-subtle px-4 py-3 text-xs text-foreground-muted"
          >
            <span>{filteredLogs.length} of {logs.length} recorded entries</span>
            <span>
              {streamState === "connected"
                ? "Live connection active"
                : streamState === "connecting" || streamState === "reconnecting"
                  ? "Reconnecting to active deployment…"
                  : streamState === "unavailable"
                    ? "Live connection unavailable; saved logs remain visible"
                    : "Saved deployment history"}
            </span>
          </div>

          <div className="max-h-[560px] min-h-64 overflow-auto bg-[hsl(222_47%_7%)] p-3 font-mono text-xs leading-6 text-[hsl(210_40%_92%)] sm:p-4">
            {filteredLogs.length === 0 ? (
              <div className="flex min-h-56 flex-col items-center justify-center text-center text-[hsl(215_18%_68%)]">
                <FileText size={24} />
                <p className="mt-3">No saved entries match this view.</p>
              </div>
            ) : (
              filteredLogs.map((log, index) => {
                const level = normalizeLevel(log.level);
                return (
                  <div
                    key={`${logKey(log)}:${index}`}
                    className="grid gap-x-3 rounded px-2 py-1 transition-colors hover:bg-white/5 sm:grid-cols-[86px_64px_1fr]"
                  >
                    <span className="text-[hsl(215_14%_58%)]">
                      {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : "—"}
                    </span>
                    <span
                      className={
                        level === "error"
                          ? "text-[hsl(0_84%_68%)]"
                          : level === "warning"
                            ? "text-[hsl(38_92%_61%)]"
                            : "text-[hsl(199_89%_63%)]"
                      }
                    >
                      {level.toUpperCase()}
                    </span>
                    <span className="break-words">{log.message}</span>
                  </div>
                );
              })
            )}
          </div>
        </section>
      )}
    </div>
  );
}

function LogsLoading({ compact = false }: { compact?: boolean }) {
  return (
    <div
      role="status"
      className={`flex items-center justify-center gap-3 rounded-xl border border-border bg-card text-sm font-medium text-foreground-muted ${
        compact ? "min-h-52" : "min-h-[55vh]"
      }`}
    >
      <Loader2 size={18} className="animate-spin text-primary" />
      Loading deployment logs…
    </div>
  );
}

function LogsPageLoading() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Diagnostics"
        title="Deployment logs"
        description="Persisted worker output is shown only for recorded deployment runs."
      />
      <LogsLoading />
    </div>
  );
}
