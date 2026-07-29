"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Activity, Clock3, Gauge, Loader2, RefreshCw, Server } from "lucide-react";
import { MetricCard } from "@/components/ui/MetricCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { ProjectSelector } from "@/components/dashboard/ProjectSelector";
import { ProjectTabs } from "@/components/dashboard/ProjectTabs";
import { useNotifications } from "@/lib/NotificationContext";
import { api, getErrorMessage, type TelemetryMetric } from "@/lib/api";

function hasRecordedTelemetry(metrics: TelemetryMetric | null) {
  if (!metrics) return false;
  return (
    metrics.cpu.length > 0 ||
    metrics.memory.length > 0 ||
    metrics.response_time !== "No data" ||
    metrics.error_rate !== "No data" ||
    metrics.uptime !== "No data"
  );
}

function latestValue(samples: { time: string; value: number }[]) {
  const latest = samples.at(-1);
  return latest ? `${latest.value.toFixed(1)}%` : "Not recorded";
}

export default function MonitoringPage() {
  return (
    <Suspense fallback={<MonitoringLoading />}>
      <MonitoringWorkspace />
    </Suspense>
  );
}

function MonitoringWorkspace() {
  const searchParams = useSearchParams();
  const { projects, isLoading: projectsLoading } = useNotifications();
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [metrics, setMetrics] = useState<TelemetryMetric | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const requestedProject = searchParams.get("project");
    if (requestedProject && projects.some((project) => project.id === requestedProject)) {
      setSelectedProjectId(requestedProject);
      return;
    }
    if (!selectedProjectId && projects.length > 0) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, searchParams, selectedProjectId]);

  const loadMetrics = useCallback(async (projectId: string) => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      setMetrics(await api.getProjectMetrics(projectId));
    } catch (requestError) {
      setMetrics(null);
      setError(getErrorMessage(requestError, "Runtime metrics could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMetrics(selectedProjectId);
  }, [loadMetrics, selectedProjectId]);

  const sampleRows = useMemo(() => {
    const times = new Set([
      ...(metrics?.cpu.map((sample) => sample.time) ?? []),
      ...(metrics?.memory.map((sample) => sample.time) ?? []),
    ]);
    return Array.from(times)
      .map((time) => ({
        time,
        cpu: metrics?.cpu.find((sample) => sample.time === time)?.value,
        memory: metrics?.memory.find((sample) => sample.time === time)?.value,
      }))
      .slice(-8)
      .reverse();
  }, [metrics]);

  if (projectsLoading) return <MonitoringLoading />;

  if (projects.length === 0) {
    return (
      <StatePanel
        title="No projects to monitor"
        description="Connect a repository or upload an application before reviewing deployment telemetry."
        action={{ label: "Connect a project", href: "/dashboard/repositories" }}
      />
    );
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const recorded = hasRecordedTelemetry(metrics);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="Runtime monitoring"
        description="Recorded deployment metrics for your selected project. Values update only when the backend receives a new telemetry sample."
        actions={
          <button
            type="button"
            onClick={() => void loadMetrics(selectedProjectId)}
            disabled={loading || !selectedProjectId}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground shadow-sm transition-colors hover:bg-surface-raised disabled:opacity-50"
          >
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        }
      />

      <ProjectSelector
        projects={projects}
        value={selectedProjectId}
        onChange={setSelectedProjectId}
        className="block max-w-sm"
      />

      {selectedProject && <ProjectTabs projectId={selectedProject.id} />}

      {error ? (
        <StatePanel
          variant="error"
          title="Monitoring data is unavailable"
          description={error}
          action={{ label: "Try again", onClick: () => void loadMetrics(selectedProjectId) }}
        />
      ) : loading ? (
        <MonitoringLoading compact />
      ) : !recorded ? (
        <StatePanel
          variant="disconnected"
          title="No runtime telemetry has been recorded"
          description="A deployment record may exist, but ZeroOps has not received CPU, memory, request, latency, or error samples for this project. No health claim is made without those signals."
        />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Runtime state"
              value={metrics?.uptime ?? "Not recorded"}
              supportingText="Latest deployment state reported with telemetry"
              icon={Server}
              tone="info"
            />
            <MetricCard
              label="Response time"
              value={metrics?.response_time ?? "Not recorded"}
              supportingText="Average across recorded samples"
              icon={Clock3}
            />
            <MetricCard
              label="Request volume"
              value={(metrics?.request_count ?? 0).toLocaleString()}
              supportingText="Total requests across recorded samples"
              icon={Activity}
            />
            <MetricCard
              label="Error rate"
              value={metrics?.error_rate ?? "Not recorded"}
              supportingText="Average across recorded samples"
              icon={Gauge}
              tone={metrics?.error_rate === "No data" ? "neutral" : "warning"}
            />
          </div>

          <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
            <div className="border-b border-border px-4 py-4 sm:px-5">
              <h2 className="text-sm font-semibold text-foreground">Recent resource samples</h2>
              <p className="mt-1 text-xs text-foreground-muted">
                Latest CPU and memory values stored for this project. Times are reported by the backend.
              </p>
            </div>
            <div className="grid gap-3 border-b border-border bg-surface-subtle p-4 sm:grid-cols-2 sm:p-5">
              <MetricCard label="Latest CPU" value={latestValue(metrics?.cpu ?? [])} icon={Gauge} />
              <MetricCard label="Latest memory" value={latestValue(metrics?.memory ?? [])} icon={Server} />
            </div>
            {sampleRows.length === 0 ? (
              <p className="px-5 py-8 text-center text-xs text-foreground-muted">
                No CPU or memory samples are stored.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[480px] text-left text-xs">
                  <thead className="bg-surface-subtle text-foreground-muted">
                    <tr>
                      <th scope="col" className="px-5 py-3 font-medium">Recorded time</th>
                      <th scope="col" className="px-5 py-3 font-medium">CPU</th>
                      <th scope="col" className="px-5 py-3 font-medium">Memory</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {sampleRows.map((row) => (
                      <tr key={row.time}>
                        <td className="px-5 py-3 font-mono text-foreground">{row.time}</td>
                        <td className="px-5 py-3 tabular-nums text-foreground-muted">
                          {row.cpu == null ? "Not recorded" : `${row.cpu.toFixed(1)}%`}
                        </td>
                        <td className="px-5 py-3 tabular-nums text-foreground-muted">
                          {row.memory == null ? "Not recorded" : `${row.memory.toFixed(1)}%`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function MonitoringLoading({ compact = false }: { compact?: boolean }) {
  return (
    <div
      role="status"
      className={`flex items-center justify-center gap-3 rounded-xl border border-border bg-card text-sm font-medium text-foreground-muted ${
        compact ? "min-h-52" : "min-h-[55vh]"
      }`}
    >
      <Loader2 size={18} className="animate-spin text-primary" />
      Loading recorded telemetry…
    </div>
  );
}
