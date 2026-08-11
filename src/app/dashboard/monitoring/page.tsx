"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Activity,
  Boxes,
  Clock3,
  Gauge,
  Loader2,
  RefreshCw,
  Server,
} from "lucide-react";
import { MetricCard } from "@/components/ui/MetricCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { ProjectSelector } from "@/components/dashboard/ProjectSelector";
import { ProjectTabs } from "@/components/dashboard/ProjectTabs";
import { useNotifications } from "@/lib/NotificationContext";
import {
  ApiError,
  api,
  getErrorMessage,
  type MonitoringSample,
  type MonitoringWindow,
  type ProjectMonitoring,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const windows: { value: MonitoringWindow; label: string }[] = [
  { value: "live", label: "Live" },
  { value: "1h", label: "1h" },
  { value: "6h", label: "6h" },
  { value: "24h", label: "24h" },
];

function formatPercent(value: number | null | undefined) {
  return value == null ? "Not recorded" : `${value.toFixed(1)}%`;
}

function formatNumber(value: number | null | undefined) {
  return value == null ? "Not recorded" : value.toLocaleString();
}

function formatLatency(value: number | null | undefined) {
  return value == null ? "Not recorded" : `${value.toFixed(0)} ms`;
}

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function latestSample(data: ProjectMonitoring | null): MonitoringSample | null {
  return data?.samples.at(-1) ?? null;
}

function hasRecordedTrend(samples: MonitoringSample[]) {
  return [
    samples.map((sample) => sample.cpu_percent),
    samples.map((sample) => sample.response_latency_ms),
    samples.map((sample) => sample.http_error_rate_percent),
  ].some((values) => values.filter((value) => typeof value === "number").length >= 2);
}

function trendPath(values: Array<number | null | undefined>) {
  const recorded = values.filter((value): value is number => typeof value === "number");
  if (recorded.length < 2) return null;
  const minimum = Math.min(...recorded);
  const maximum = Math.max(...recorded);
  const range = maximum - minimum || 1;
  let drawing = false;

  return values
    .map((value, index) => {
      if (typeof value !== "number") {
        drawing = false;
        return "";
      }
      const x = values.length === 1 ? 0 : (index / (values.length - 1)) * 100;
      const y = 38 - ((value - minimum) / range) * 34;
      const command = drawing ? "L" : "M";
      drawing = true;
      return `${command}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .filter(Boolean)
    .join(" ");
}

function TrendCard({
  label,
  values,
  latestValue,
  description,
  tone = "primary",
}: {
  label: string;
  values: Array<number | null | undefined>;
  latestValue: string;
  description: string;
  tone?: "primary" | "info" | "warning";
}) {
  const path = trendPath(values);
  if (!path) return null;
  const stroke =
    tone === "warning" ? "var(--warning)" : tone === "info" ? "var(--info)" : "var(--primary)";

  return (
    <article className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-foreground">{label}</h3>
          <p className="mt-1 text-xs text-foreground-muted">{description}</p>
        </div>
        <p className="shrink-0 font-mono text-sm font-semibold text-foreground tabular-nums">
          {latestValue}
        </p>
      </div>
      <svg
        viewBox="0 0 100 42"
        preserveAspectRatio="none"
        role="img"
        aria-label={`${label} across ${values.length} recorded samples; latest value ${latestValue}`}
        className="mt-4 h-20 w-full overflow-visible"
      >
        <path d="M0,40 L100,40" fill="none" stroke="var(--border)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        <path
          d={path}
          fill="none"
          stroke={stroke}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </article>
  );
}

export default function MonitoringPage() {
  return (
    <Suspense fallback={<MonitoringPageLoading />}>
      <MonitoringWorkspace />
    </Suspense>
  );
}

function MonitoringWorkspace() {
  const searchParams = useSearchParams();
  const { projects, isLoading: projectsLoading } = useNotifications();
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [window, setWindow] = useState<MonitoringWindow>("live");
  const [monitoring, setMonitoring] = useState<ProjectMonitoring | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [responseState, setResponseState] = useState<
    "idle" | "available" | "no_record" | "no_telemetry" | "unavailable" | "error"
  >("idle");
  const requestSequence = useRef(0);

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

  const loadMonitoring = useCallback(async (projectId: string, selectedWindow: MonitoringWindow) => {
    if (!projectId) return;
    const requestId = ++requestSequence.current;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getProjectMonitoring(projectId, selectedWindow);
      if (requestId !== requestSequence.current) return;
      setMonitoring(data);
      setResponseState(data.availability === "available" ? "available" : data.availability);
    } catch (requestError) {
      if (requestId !== requestSequence.current) return;
      setMonitoring(null);
      if (requestError instanceof ApiError && requestError.status === 404) {
        setResponseState("no_record");
      } else if (requestError instanceof ApiError && requestError.status === 503) {
        setResponseState("unavailable");
        setError(getErrorMessage(requestError, "The telemetry provider is unavailable."));
      } else {
        setResponseState("error");
        setError(getErrorMessage(requestError, "Runtime metrics could not be loaded."));
      }
    } finally {
      if (requestId === requestSequence.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMonitoring(selectedProjectId, window);
  }, [loadMonitoring, selectedProjectId, window]);

  const rows = useMemo(
    () => [...(monitoring?.samples ?? [])].slice(-12).reverse(),
    [monitoring],
  );

  if (projectsLoading) return <MonitoringPageLoading />;

  if (projects.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Operations"
          title="Runtime monitoring"
          description="Recorded telemetry is shown only when a configured collector returns samples."
        />
        <StatePanel
          title="No projects to monitor"
          description="Connect a repository or upload an application before reviewing deployment telemetry."
          action={{ label: "Connect a project", href: "/dashboard/repositories" }}
        />
      </div>
    );
  }

  if (!selectedProjectId) return <MonitoringPageLoading />;

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const latest = latestSample(monitoring);
  const availableWindows = new Set<MonitoringWindow>(
    monitoring?.available_windows?.length
      ? monitoring.available_windows
      : [monitoring?.window ?? "live"],
  );
  const noTelemetry =
    responseState === "no_record" ||
    responseState === "no_telemetry" ||
    (responseState === "available" && monitoring?.samples.length === 0);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="Runtime monitoring"
        description="Recorded telemetry for the selected window. Values are shown only when a configured collector returns samples."
        actions={
          <button
            type="button"
            onClick={() => void loadMonitoring(selectedProjectId, window)}
            disabled={loading || !selectedProjectId}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground shadow-sm transition-colors hover:bg-surface-raised disabled:opacity-50"
          >
            <RefreshCw size={15} className={loading ? "animate-spin motion-reduce:animate-none" : ""} aria-hidden="true" />
            Refresh
          </button>
        }
      />

      <section aria-label="Monitoring context" className="rounded-xl border border-border bg-card p-4 shadow-sm sm:p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <ProjectSelector
            projects={projects}
            value={selectedProjectId}
            onChange={setSelectedProjectId}
            className="block w-full max-w-sm"
          />
          <div>
            <span className="mb-1.5 block text-xs font-semibold text-foreground-muted">
              Telemetry window
            </span>
            <div role="group" aria-label="Telemetry window" className="inline-flex rounded-lg border border-border bg-surface-subtle p-1">
              {windows.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={window === option.value}
                  aria-label={
                    availableWindows.has(option.value)
                      ? `${option.label} telemetry window`
                      : `${option.label} telemetry window unavailable`
                  }
                  onClick={() => setWindow(option.value)}
                  disabled={loading || !availableWindows.has(option.value)}
                  title={availableWindows.has(option.value) ? undefined : "No stored telemetry is available for this window."}
                  className={cn(
                    "min-h-11 min-w-12 rounded-md px-3 text-xs font-semibold transition-colors disabled:opacity-50",
                    window === option.value
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-foreground-muted hover:bg-card hover:text-foreground",
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        {selectedProject && (
          <div className="mt-5">
            <ProjectTabs projectId={selectedProject.id} />
          </div>
        )}
      </section>

      {loading ? (
        <MonitoringLoading compact />
      ) : responseState === "unavailable" || monitoring?.availability === "unavailable" ? (
        <StatePanel
          variant="disconnected"
          title="Telemetry provider unavailable"
          description={error || monitoring?.message || "The configured monitoring source did not return data. No health or availability claim is made."}
          action={{ label: "Try again", onClick: () => void loadMonitoring(selectedProjectId, window) }}
        />
      ) : responseState === "error" ? (
        <StatePanel
          variant="error"
          title="Monitoring request failed"
          description={error || "Runtime telemetry could not be loaded."}
          action={{ label: "Try again", onClick: () => void loadMonitoring(selectedProjectId, window) }}
        />
      ) : noTelemetry ? (
        <StatePanel
          variant="disconnected"
          title="No telemetry received"
          description={monitoring?.message || `No monitoring samples are stored for the ${window === "live" ? "live" : window} window. This is not evidence that the service is healthy or available.`}
        />
      ) : monitoring && latest ? (
        <>
          <section aria-label="Application telemetry summary" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Application health"
              value={monitoring.deployment_health || "Not recorded"}
              supportingText="Latest collector-reported deployment health"
              icon={Server}
              tone={monitoring.deployment_health === "healthy" ? "success" : "neutral"}
            />
            <MetricCard
              label="Availability"
              value={formatPercent(latest.availability_percent)}
              supportingText={`Recorded for the ${window} window`}
              icon={Gauge}
            />
            <MetricCard
              label="Response latency"
              value={formatLatency(latest.response_latency_ms)}
              supportingText="Latest recorded response latency"
              icon={Clock3}
            />
            <MetricCard
              label="Request rate"
              value={formatNumber(latest.request_rate)}
              supportingText="Latest source-reported request rate"
              icon={Activity}
            />
            <MetricCard label="CPU" value={formatPercent(latest.cpu_percent)} supportingText="Latest recorded utilization" icon={Gauge} />
            <MetricCard label="Memory" value={formatPercent(latest.memory_percent)} supportingText="Latest recorded utilization" icon={Server} />
            <MetricCard label="HTTP error rate" value={formatPercent(latest.http_error_rate_percent)} supportingText="Latest recorded error rate" icon={Activity} tone={(latest.http_error_rate_percent ?? 0) > 0 ? "warning" : "neutral"} />
            <MetricCard label="Deployment revision" value={monitoring.deployment_revision || "Not recorded"} supportingText={monitoring.target_provider || "Deployment target not recorded"} icon={Boxes} />
          </section>

          {hasRecordedTrend(monitoring.samples.slice(-12)) && (
            <section aria-labelledby="telemetry-trends-heading">
              <div className="mb-3">
                <h2 id="telemetry-trends-heading" className="text-base font-semibold text-foreground">
                  Recorded trends
                </h2>
                <p className="mt-1 text-xs text-foreground-muted">
                  Shape-only summaries of the samples below; exact values remain available in the table.
                </p>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                <TrendCard
                  label="CPU utilization"
                  values={monitoring.samples.slice(-12).map((sample) => sample.cpu_percent)}
                  latestValue={formatPercent(latest.cpu_percent)}
                  description="Oldest to newest"
                />
                <TrendCard
                  label="Response latency"
                  values={monitoring.samples.slice(-12).map((sample) => sample.response_latency_ms)}
                  latestValue={formatLatency(latest.response_latency_ms)}
                  description="Oldest to newest"
                  tone="info"
                />
                <TrendCard
                  label="HTTP error rate"
                  values={monitoring.samples.slice(-12).map((sample) => sample.http_error_rate_percent)}
                  latestValue={formatPercent(latest.http_error_rate_percent)}
                  description="Oldest to newest"
                  tone="warning"
                />
              </div>
            </section>
          )}

          {monitoring.target_provider === "azure-aks" && (
            <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
              <div className="flex items-center gap-2">
                <Boxes size={17} className="text-primary" aria-hidden="true" />
                <h2 className="text-sm font-semibold text-foreground">AKS workload telemetry</h2>
              </div>
              <dl className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {[
                  ["Pods ready", formatNumber(latest.pods_ready)],
                  ["Pod restarts", formatNumber(latest.pod_restarts)],
                  ["Replica count", formatNumber(latest.replica_count)],
                  ["Failed pods", formatNumber(latest.failed_pods)],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg border border-border bg-surface-subtle px-3 py-3">
                    <dt className="text-xs font-medium text-foreground-subtle">{label}</dt>
                    <dd className="mt-1 font-mono text-sm font-semibold tabular-nums text-foreground">{value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}

          <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
            <div className="border-b border-border px-4 py-4 sm:px-5">
              <h2 className="text-sm font-semibold text-foreground">Recorded samples</h2>
              <p className="mt-1 text-xs text-foreground-muted">
                Latest twelve samples returned for this window{monitoring.source ? ` by ${monitoring.source}` : ""}.
              </p>
            </div>
            <div className="grid divide-y divide-border md:hidden">
              {rows.map((sample, index) => (
                <dl key={`${sample.recorded_at}-mobile-${index}`} className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-4 text-xs">
                  <div className="col-span-2">
                    <dt className="text-foreground-subtle">Recorded time</dt>
                    <dd className="mt-1 font-mono text-foreground">{formatTime(sample.recorded_at)}</dd>
                  </div>
                  <div><dt className="text-foreground-subtle">CPU</dt><dd className="mt-1 tabular-nums text-foreground">{formatPercent(sample.cpu_percent)}</dd></div>
                  <div><dt className="text-foreground-subtle">Memory</dt><dd className="mt-1 tabular-nums text-foreground">{formatPercent(sample.memory_percent)}</dd></div>
                  <div><dt className="text-foreground-subtle">Latency</dt><dd className="mt-1 tabular-nums text-foreground">{formatLatency(sample.response_latency_ms)}</dd></div>
                  <div><dt className="text-foreground-subtle">Errors</dt><dd className="mt-1 tabular-nums text-foreground">{formatPercent(sample.http_error_rate_percent)}</dd></div>
                </dl>
              ))}
            </div>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full min-w-[760px] text-left text-xs">
                <caption className="sr-only">Recorded monitoring samples for the selected telemetry window</caption>
                <thead className="bg-surface-subtle text-foreground-muted">
                  <tr>
                    <th scope="col" className="px-5 py-3 font-medium">Recorded time</th>
                    <th scope="col" className="px-5 py-3 font-medium">CPU</th>
                    <th scope="col" className="px-5 py-3 font-medium">Memory</th>
                    <th scope="col" className="px-5 py-3 font-medium">Latency</th>
                    <th scope="col" className="px-5 py-3 font-medium">Request rate</th>
                    <th scope="col" className="px-5 py-3 font-medium">Errors</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {rows.map((sample, index) => (
                    <tr key={`${sample.recorded_at}-${index}`} className="transition-colors hover:bg-surface-subtle/70">
                      <td className="px-5 py-3 font-mono text-foreground">{formatTime(sample.recorded_at)}</td>
                      <td className="px-5 py-3 tabular-nums text-foreground-muted">{formatPercent(sample.cpu_percent)}</td>
                      <td className="px-5 py-3 tabular-nums text-foreground-muted">{formatPercent(sample.memory_percent)}</td>
                      <td className="px-5 py-3 tabular-nums text-foreground-muted">{formatLatency(sample.response_latency_ms)}</td>
                      <td className="px-5 py-3 tabular-nums text-foreground-muted">{formatNumber(sample.request_rate)}</td>
                      <td className="px-5 py-3 tabular-nums text-foreground-muted">{formatPercent(sample.http_error_rate_percent)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold text-foreground">Latest incidents</h2>
                <p className="mt-1 text-xs text-foreground-muted">Incidents linked by the monitoring API for this project.</p>
              </div>
              <Link href={`/dashboard/incidents?project=${selectedProjectId}`} className="inline-flex min-h-11 items-center rounded-lg border border-border px-3 text-xs font-semibold text-foreground hover:bg-surface-raised">
                View incidents
              </Link>
            </div>
            {(monitoring.latest_incidents ?? []).length === 0 ? (
              <p className="mt-4 rounded-lg border border-border bg-surface-subtle px-3 py-3 text-xs text-foreground-muted">
                No incidents were returned for this window. This is not proof that the service had no incidents.
              </p>
            ) : (
              <ul className="mt-4 divide-y divide-border rounded-lg border border-border">
                {(monitoring.latest_incidents ?? []).slice(0, 3).map((incident) => (
                  <li key={incident.id} className="flex flex-col gap-1 px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                    <span className="text-xs font-medium text-foreground">{incident.title}</span>
                    <span className="text-xs font-semibold capitalize text-foreground-muted">{incident.severity} · {incident.status}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      ) : (
        <StatePanel
          variant="info"
          title="Monitoring response incomplete"
          description="The backend returned no usable sample or explicit unavailable state. Refresh to request the window again."
          action={{ label: "Refresh", onClick: () => void loadMonitoring(selectedProjectId, window) }}
        />
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
      <Loader2 size={18} className="animate-spin text-primary motion-reduce:animate-none" aria-hidden="true" />
      Loading recorded telemetry…
      <span className="sr-only">Please wait.</span>
    </div>
  );
}

function MonitoringPageLoading() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="Runtime monitoring"
        description="Recorded telemetry is shown only when a configured collector returns samples."
      />
      <MonitoringLoading />
    </div>
  );
}
