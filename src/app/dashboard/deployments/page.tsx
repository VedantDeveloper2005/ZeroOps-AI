"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Circle,
  Copy,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCw,
  RotateCcw,
  ServerCog,
  Wifi,
  WifiOff,
  XCircle,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ProjectTabs } from "@/components/dashboard/ProjectTabs";
import {
  api,
  type Deployment,
  type DeploymentDetail,
  type FailureAnalysis,
} from "@/lib/api";
import { useNotifications } from "@/lib/NotificationContext";
import { createReconnectingWebSocket } from "@/lib/runtime-config";
import { cn } from "@/lib/utils";

type StageStatus = "pending" | "active" | "completed" | "failed";

interface RecordedStage {
  id: number;
  label: string;
  status: StageStatus;
  duration: string;
}

type LogLineType =
  | "command"
  | "debug"
  | "info"
  | "success"
  | "warning"
  | "error";

interface LogLine {
  key: string;
  text: string;
  type: LogLineType;
  lineNumber: number | null;
  timestamp: string | null;
}

type StreamState =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "unavailable"
  | "complete";

interface DeploymentStreamEvent {
  type?: unknown;
  id?: unknown;
  label?: unknown;
  status?: unknown;
  duration?: unknown;
  text?: unknown;
  lineType?: unknown;
  line_number?: unknown;
}

const terminalStatuses = new Set<Deployment["status"]>([
  "running",
  "failed",
  "stopped",
  "rolled_back",
]);

const inProgressStatuses = new Set<Deployment["status"]>([
  "queued",
  "building",
  "deploying",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStageStatus(value: unknown): value is StageStatus {
  return (
    value === "pending" ||
    value === "active" ||
    value === "completed" ||
    value === "failed"
  );
}

function isDeploymentStatus(value: unknown): value is Deployment["status"] {
  return (
    value === "queued" ||
    value === "building" ||
    value === "deploying" ||
    value === "running" ||
    value === "failed" ||
    value === "stopped" ||
    value === "rolled_back"
  );
}

function parseRecordedStages(value: unknown): RecordedStage[] {
  if (!Array.isArray(value)) return [];

  return value.flatMap((item) => {
    if (!isRecord(item)) return [];
    if (
      typeof item.id !== "number" ||
      !Number.isFinite(item.id) ||
      typeof item.label !== "string" ||
      !item.label.trim() ||
      !isStageStatus(item.status)
    ) {
      return [];
    }

    return [
      {
        id: item.id,
        label: item.label.trim(),
        status: item.status,
        duration: typeof item.duration === "string" ? item.duration.trim() : "",
      },
    ];
  });
}

function normalizeLogType(value: unknown): LogLineType {
  if (typeof value !== "string") return "info";

  switch (value.toLowerCase()) {
    case "command":
      return "command";
    case "debug":
      return "debug";
    case "success":
      return "success";
    case "warn":
    case "warning":
      return "warning";
    case "error":
      return "error";
    default:
      return "info";
  }
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function deploymentDuration(deployment: Deployment): string {
  if (deployment.duration) return deployment.duration;
  if (deployment.duration_seconds != null) {
    return `${deployment.duration_seconds}s`;
  }
  return "Not recorded";
}

function shortCommit(commit: string | null): string {
  return commit ? commit.slice(0, 8) : "Not recorded";
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function safeExternalUrl(value: string | null): string | null {
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

function metadataValue(
  metadata: Record<string, unknown> | null | undefined,
  path: string[],
): string | null {
  let current: unknown = metadata;
  for (const key of path) {
    if (!isRecord(current)) return null;
    current = current[key];
  }

  if (typeof current === "string" && current.trim()) return current.trim();
  if (typeof current === "number" && Number.isFinite(current)) {
    return String(current);
  }
  return null;
}

function deploymentHref(deployment: Deployment): string {
  const params = new URLSearchParams({ id: deployment.id });
  if (deployment.project_id) params.set("project", deployment.project_id);
  if (deployment.project_name) params.set("repo", deployment.project_name);
  return `/dashboard/deployments?${params.toString()}`;
}

function statusDescription(status: Deployment["status"]): string {
  switch (status) {
    case "queued":
      return "The deployment record is waiting for execution.";
    case "building":
      return "The backend reports that build work is in progress.";
    case "deploying":
      return "The backend reports that deployment work is in progress.";
    case "running":
      return "The backend recorded this deployment as running.";
    case "failed":
      return "The backend recorded this deployment as failed.";
    case "stopped":
      return "The backend recorded this deployment as stopped.";
    case "rolled_back":
      return "The backend recorded this deployment as rolled back.";
  }
}

function stageLabel(status: StageStatus): string {
  switch (status) {
    case "active":
      return "In progress";
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
    default:
      return "Pending";
  }
}

function StageStatusIcon({ status }: { status: StageStatus }) {
  if (status === "completed") {
    return <CheckCircle2 size={18} aria-hidden="true" />;
  }
  if (status === "active") {
    return (
      <Loader2
        size={18}
        className="animate-spin motion-reduce:animate-none"
        aria-hidden="true"
      />
    );
  }
  if (status === "failed") {
    return <XCircle size={18} aria-hidden="true" />;
  }
  return <Circle size={16} aria-hidden="true" />;
}

function StageTimeline({
  stages,
  deploymentStatus,
}: {
  stages: RecordedStage[];
  deploymentStatus: Deployment["status"];
}) {
  const completedCount = stages.filter(
    (stage) => stage.status === "completed",
  ).length;
  const activeStage = stages.find((stage) => stage.status === "active");
  const nextPendingStage = stages.find((stage) => stage.status === "pending");

  return (
    <section
      aria-labelledby="deployment-stages-heading"
      className="rounded-xl border border-border bg-card shadow-sm"
    >
      <div className="border-b border-border px-4 py-4 sm:px-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3
              id="deployment-stages-heading"
              className="text-sm font-semibold text-foreground"
            >
              Recorded execution stages
            </h3>
            <p className="mt-1 text-xs leading-5 text-foreground-muted">
              Only stages stored by the deployment backend are shown. Stage
              start times are not provided by the current API.
            </p>
          </div>
          {stages.length > 0 && (
            <p className="shrink-0 text-xs font-medium text-foreground-muted">
              {completedCount} of {stages.length} completed
            </p>
          )}
        </div>

        {stages.length > 0 && (
          <div className="mt-4">
            <div
              role="progressbar"
              aria-label="Recorded stage completion"
              aria-valuemin={0}
              aria-valuemax={stages.length}
              aria-valuenow={completedCount}
              className="h-1.5 overflow-hidden rounded-full bg-surface-raised"
            >
              <div
                className="h-full rounded-full bg-success"
                style={{
                  width: `${Math.round(
                    (completedCount / stages.length) * 100,
                  )}%`,
                }}
              />
            </div>
            <p className="mt-2 text-xs text-foreground-muted">
              {activeStage
                ? `Active stage: ${activeStage.label}`
                : nextPendingStage && inProgressStatuses.has(deploymentStatus)
                  ? `Next recorded pending stage: ${nextPendingStage.label}`
                  : "No active stage is currently recorded."}
            </p>
          </div>
        )}
      </div>

      {stages.length === 0 ? (
        <div className="px-4 py-5 sm:px-5">
          <StatePanel
            compact
            title={
              inProgressStatuses.has(deploymentStatus)
                ? "Stage details pending"
                : "Stage details unavailable"
            }
            description={
              inProgressStatuses.has(deploymentStatus)
                ? "The deployment exists, but the backend has not recorded a stage timeline yet."
                : "This deployment has no recorded stage timeline. No completion stages have been inferred."
            }
          />
        </div>
      ) : (
        <ol className="divide-y divide-border/70 px-4 sm:px-5">
          {stages.map((stage, index) => (
            <li
              key={`${stage.id}-${index}`}
              className="grid grid-cols-[2.25rem_minmax(0,1fr)] gap-3 py-4"
            >
              <div
                className={cn(
                  "mt-0.5 flex h-8 w-8 items-center justify-center rounded-full border",
                  stage.status === "completed" &&
                    "border-success/30 bg-success-subtle text-success",
                  stage.status === "active" &&
                    "border-info/30 bg-info-subtle text-info",
                  stage.status === "failed" &&
                    "border-danger/30 bg-danger-subtle text-danger",
                  stage.status === "pending" &&
                    "border-border bg-surface-subtle text-foreground-subtle",
                )}
              >
                <StageStatusIcon status={stage.status} />
              </div>
              <div className="min-w-0 sm:flex sm:items-start sm:justify-between sm:gap-4">
                <div className="min-w-0">
                  <p className="break-words text-sm font-medium text-foreground">
                    {stage.label}
                  </p>
                  <p className="mt-0.5 text-xs text-foreground-muted">
                    Stage {stage.id} · {stageLabel(stage.status)}
                  </p>
                </div>
                <p className="mt-2 shrink-0 font-mono text-xs text-foreground-muted sm:mt-0">
                  {stage.duration && stage.duration !== "..."
                    ? stage.duration
                    : "Duration pending"}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function streamStatePresentation(state: StreamState): {
  label: string;
  icon: typeof Wifi;
  className: string;
} {
  switch (state) {
    case "connecting":
      return {
        label: "Connecting to live updates",
        icon: Loader2,
        className: "text-info",
      };
    case "connected":
      return {
        label: "Live updates connected",
        icon: Wifi,
        className: "text-success",
      };
    case "reconnecting":
      return {
        label: "Live updates reconnecting",
        icon: RefreshCw,
        className: "text-warning",
      };
    case "unavailable":
      return {
        label: "Live updates unavailable",
        icon: WifiOff,
        className: "text-warning",
      };
    case "complete":
      return {
        label: "Persisted deployment logs",
        icon: FileText,
        className: "text-foreground-muted",
      };
    default:
      return {
        label: "Persisted deployment logs",
        icon: FileText,
        className: "text-foreground-muted",
      };
  }
}

function logLineClass(type: LogLineType): string {
  switch (type) {
    case "command":
      return "text-zinc-100";
    case "success":
      return "text-emerald-300";
    case "warning":
      return "text-amber-300";
    case "error":
      return "text-red-300";
    case "debug":
      return "text-sky-300";
    default:
      return "text-zinc-300";
  }
}

function logPrefix(type: LogLineType): string {
  switch (type) {
    case "command":
      return "COMMAND";
    case "success":
      return "SUCCESS";
    case "warning":
      return "WARN";
    case "error":
      return "ERROR";
    case "debug":
      return "DEBUG";
    default:
      return "INFO";
  }
}

function DeploymentLogs({
  lines,
  open,
  onToggle,
  onCopy,
  streamState,
}: {
  lines: LogLine[];
  open: boolean;
  onToggle: () => void;
  onCopy: () => void;
  streamState: StreamState;
}) {
  const logRef = useRef<HTMLDivElement>(null);
  const presentation = streamStatePresentation(streamState);
  const StreamIcon = presentation.icon;

  useEffect(() => {
    if (!open || !logRef.current) return;
    logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines, open]);

  return (
    <section
      id="deployment-logs"
      aria-labelledby="deployment-logs-heading"
      className="overflow-hidden rounded-xl border border-border bg-card shadow-sm"
    >
      <div className="flex flex-col gap-3 border-b border-border px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <div>
          <h3
            id="deployment-logs-heading"
            className="text-sm font-semibold text-foreground"
          >
            Deployment logs
          </h3>
          <p
            role="status"
            className={cn(
              "mt-1 flex items-center gap-1.5 text-xs",
              presentation.className,
            )}
          >
            <StreamIcon
              size={13}
              className={cn(
                (streamState === "connecting" ||
                  streamState === "reconnecting") &&
                  "animate-spin motion-reduce:animate-none",
              )}
              aria-hidden="true"
            />
            {presentation.label}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onCopy}
            disabled={lines.length === 0}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground transition-colors hover:bg-card-hover disabled:opacity-50"
          >
            <Copy size={14} aria-hidden="true" />
            Copy logs
          </button>
          <button
            type="button"
            aria-expanded={open}
            aria-controls="deployment-log-content"
            onClick={onToggle}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground transition-colors hover:bg-card-hover"
          >
            {open ? "Hide logs" : `Show logs (${lines.length})`}
            {open ? (
              <ChevronUp size={15} aria-hidden="true" />
            ) : (
              <ChevronDown size={15} aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      {streamState === "unavailable" && (
        <div
          role="status"
          className="border-b border-warning/25 bg-warning-subtle px-4 py-3 text-xs leading-5 text-foreground sm:px-5"
        >
          The live stream could not be restored. Persisted logs remain available;
          refresh the deployment to load any newer records.
        </div>
      )}

      {open && (
        <div
          id="deployment-log-content"
          ref={logRef}
          role="log"
          aria-live="polite"
          aria-relevant="additions"
          aria-label="Deployment log output"
          tabIndex={0}
          className="max-h-[26rem] min-h-52 overflow-y-auto bg-zinc-950 p-4 font-mono text-xs leading-6 text-zinc-200 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary sm:p-5"
        >
          {lines.length === 0 ? (
            <p className="text-zinc-400">
              No deployment logs have been recorded yet.
            </p>
          ) : (
            lines.map((line) => (
              <div
                key={line.key}
                className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 border-b border-white/5 py-1 last:border-0"
              >
                <span
                  aria-hidden="true"
                  className="select-none text-right text-zinc-600"
                >
                  {line.lineNumber ?? "·"}
                </span>
                <p className={cn("min-w-0 whitespace-pre-wrap break-words", logLineClass(line.type))}>
                  <span className="mr-2 font-semibold">[{logPrefix(line.type)}]</span>
                  {line.timestamp && (
                    <time
                      dateTime={line.timestamp}
                      className="mr-2 text-zinc-500"
                    >
                      {formatDateTime(line.timestamp)}
                    </time>
                  )}
                  {line.text}
                </p>
              </div>
            ))
          )}
        </div>
      )}
    </section>
  );
}

function HistorySkeleton() {
  return (
    <div className="space-y-3" aria-label="Loading deployment history">
      {[0, 1, 2].map((item) => (
        <div
          key={item}
          className="h-20 animate-pulse rounded-lg bg-surface-subtle motion-reduce:animate-none"
        />
      ))}
    </div>
  );
}

function DeploymentsPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const deployId = searchParams.get("id");
  const requestedProjectId = searchParams.get("project");
  const { addToast, addNotification, refreshStats } = useNotifications();

  const [history, setHistory] = useState<Deployment[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const [currentDeployment, setCurrentDeployment] =
    useState<DeploymentDetail | null>(null);
  const [selectedLoading, setSelectedLoading] = useState(false);
  const [selectedError, setSelectedError] = useState<string | null>(null);
  const [stages, setStages] = useState<RecordedStage[]>([]);
  const [logLines, setLogLines] = useState<LogLine[]>([]);
  const [logsOpen, setLogsOpen] = useState(true);
  const [streamState, setStreamState] = useState<StreamState>("idle");

  const [failureAnalysis, setFailureAnalysis] =
    useState<FailureAnalysis | null>(null);
  const [failureAnalysisLoading, setFailureAnalysisLoading] = useState(false);
  const [failureAnalysisError, setFailureAnalysisError] = useState<string | null>(
    null,
  );
  const [resolutionOpen, setResolutionOpen] = useState(false);

  const [redeploying, setRedeploying] = useState(false);
  const [requestingPaidFix, setRequestingPaidFix] = useState(false);
  const [paidFixConfirmationOpen, setPaidFixConfirmationOpen] = useState(false);
  const paidFixDialogRef = useRef<HTMLDialogElement>(null);
  const liveLogSequence = useRef(0);

  const fetchHistory = useCallback(async (showLoading = true) => {
    if (showLoading) setHistoryLoading(true);
    try {
      const deployments = await api.getDeployments(20);
      setHistory(deployments);
      setHistoryError(null);
    } catch (error) {
      setHistoryError(
        getErrorMessage(error, "Deployment history could not be loaded."),
      );
      if (showLoading) setHistory([]);
    } finally {
      if (showLoading) setHistoryLoading(false);
    }
  }, []);

  const applyDeploymentDetail = useCallback((detail: DeploymentDetail) => {
    setCurrentDeployment(detail);
    setStages(parseRecordedStages(detail.infrastructure_metadata?.stages));
    setLogLines(
      detail.logs.map((log, index) => ({
        key: `persisted-${log.line_number}-${index}`,
        text: log.message,
        type: normalizeLogType(log.level),
        lineNumber: log.line_number,
        timestamp: log.timestamp,
      })),
    );
  }, []);

  const refreshSelectedDeployment = useCallback(async () => {
    if (!deployId) return;
    setSelectedLoading(true);
    setSelectedError(null);
    try {
      const detail = await api.getDeployment(deployId);
      applyDeploymentDetail(detail);
      setStreamState(
        terminalStatuses.has(detail.status) ? "complete" : "unavailable",
      );
    } catch (error) {
      setSelectedError(
        getErrorMessage(error, "The selected deployment could not be loaded."),
      );
    } finally {
      setSelectedLoading(false);
    }
  }, [applyDeploymentDetail, deployId]);

  useEffect(() => {
    void fetchHistory();
  }, [fetchHistory]);

  useEffect(() => {
    setPaidFixConfirmationOpen(false);
    setResolutionOpen(false);
    setFailureAnalysis(null);
    setFailureAnalysisError(null);
    liveLogSequence.current = 0;

    if (!deployId) {
      setCurrentDeployment(null);
      setSelectedError(null);
      setSelectedLoading(false);
      setStages([]);
      setLogLines([]);
      setStreamState("idle");
      return;
    }

    const selectedDeploymentId = deployId;
    let active = true;
    let disposeSocket: (() => void) | null = null;
    let refreshTimer: ReturnType<typeof setTimeout> | null = null;

    setCurrentDeployment(null);
    setSelectedError(null);
    setSelectedLoading(true);
    setStages([]);
    setLogLines([]);
    setStreamState("idle");

    async function loadDeploymentAndStream() {
      let detail: DeploymentDetail;
      try {
        detail = await api.getDeployment(selectedDeploymentId);
      } catch (error) {
        if (!active) return;
        setSelectedError(
          getErrorMessage(error, "The selected deployment could not be loaded."),
        );
        setSelectedLoading(false);
        return;
      }

      if (!active) return;
      applyDeploymentDetail(detail);
      setLogsOpen(detail.status !== "running");
      setSelectedLoading(false);

      if (terminalStatuses.has(detail.status)) {
        setStreamState("complete");
        return;
      }

      setStreamState("connecting");
      disposeSocket = createReconnectingWebSocket(
        `/ws/deployments/${selectedDeploymentId}`,
        {
          onOpen: () => {
            if (active) setStreamState("connected");
          },
          onMessage: (event) => {
            if (!active) return;
            try {
              const data = JSON.parse(event.data) as DeploymentStreamEvent;

              if (
                data.type === "stage" &&
                typeof data.id === "number" &&
                Number.isFinite(data.id) &&
                isStageStatus(data.status)
              ) {
                const eventLabel =
                  typeof data.label === "string" && data.label.trim()
                    ? data.label.trim()
                    : null;
                const eventDuration =
                  typeof data.duration === "string" ? data.duration.trim() : "";

                setStages((previous) => {
                  const existingIndex = previous.findIndex(
                    (stage) => stage.id === data.id,
                  );
                  if (existingIndex === -1) {
                    if (!eventLabel) return previous;
                    return [
                      ...previous,
                      {
                        id: data.id as number,
                        label: eventLabel,
                        status: data.status as StageStatus,
                        duration: eventDuration,
                      },
                    ];
                  }

                  return previous.map((stage, index) =>
                    index === existingIndex
                      ? {
                          ...stage,
                          label: eventLabel ?? stage.label,
                          status: data.status as StageStatus,
                          duration:
                            typeof data.duration === "string"
                              ? eventDuration
                              : stage.duration,
                        }
                      : stage,
                  );
                });
              }

              if (data.type === "log" && typeof data.text === "string") {
                const logText = data.text;
                liveLogSequence.current += 1;
                setLogLines((previous) => [
                  ...previous,
                  {
                    key: `live-${liveLogSequence.current}`,
                    text: logText,
                    type: normalizeLogType(data.lineType),
                    lineNumber:
                      typeof data.line_number === "number" &&
                      Number.isFinite(data.line_number)
                        ? data.line_number
                        : null,
                    timestamp: null,
                  },
                ]);
              }

              if (
                data.type === "status" &&
                isDeploymentStatus(data.status)
              ) {
                const nextStatus = data.status;
                setCurrentDeployment((previous) =>
                  previous ? { ...previous, status: nextStatus } : previous,
                );

                if (terminalStatuses.has(nextStatus)) {
                  setStreamState("complete");
                  disposeSocket?.();
                  disposeSocket = null;
                }

                void fetchHistory(false);
                refreshStats();

                if (nextStatus === "running") {
                  addToast(
                    "The backend recorded the deployment as running.",
                    "success",
                  );
                  addNotification({
                    title: "Deployment running",
                    message: `Deployment ${selectedDeploymentId} is now recorded as running.`,
                    type: "success",
                    category: "deployment",
                    action_url: `/dashboard/deployments?id=${selectedDeploymentId}`,
                  });
                } else if (nextStatus === "failed") {
                  addToast(
                    "The deployment failed. Review its recorded diagnostics and logs.",
                    "error",
                  );
                }

                if (terminalStatuses.has(nextStatus)) {
                  refreshTimer = setTimeout(() => {
                    void api
                      .getDeployment(selectedDeploymentId)
                      .then((refreshed) => {
                        if (active) {
                          applyDeploymentDetail(refreshed);
                          void fetchHistory(false);
                        }
                      })
                      .catch(() => {
                        // The WebSocket status remains authoritative for this view.
                      });
                  }, 300);
                }
              }
            } catch {
              // Ignore malformed events; persisted records remain available.
            }
          },
          onError: () => {
            if (active) setStreamState("reconnecting");
          },
          onClose: () => {
            if (active) setStreamState("unavailable");
          },
        },
      );
    }

    void loadDeploymentAndStream();

    return () => {
      active = false;
      if (refreshTimer) clearTimeout(refreshTimer);
      disposeSocket?.();
    };
  }, [
    addNotification,
    addToast,
    applyDeploymentDetail,
    deployId,
    fetchHistory,
    refreshStats,
  ]);

  useEffect(() => {
    if (!deployId || currentDeployment?.status !== "failed") {
      setFailureAnalysis(null);
      setFailureAnalysisError(null);
      setFailureAnalysisLoading(false);
      return;
    }

    let active = true;
    setFailureAnalysis(null);
    setFailureAnalysisError(null);
    setFailureAnalysisLoading(true);

    api
      .getDeploymentFailureAnalysis(deployId)
      .then((analysis) => {
        if (active) setFailureAnalysis(analysis);
      })
      .catch((error) => {
        if (active) {
          setFailureAnalysisError(
            getErrorMessage(
              error,
              "No failure analysis is available for this deployment.",
            ),
          );
        }
      })
      .finally(() => {
        if (active) setFailureAnalysisLoading(false);
      });

    return () => {
      active = false;
    };
  }, [currentDeployment?.status, deployId]);

  useEffect(() => {
    const dialog = paidFixDialogRef.current;
    if (!dialog) return;

    if (paidFixConfirmationOpen && !dialog.open) {
      dialog.showModal();
    } else if (!paidFixConfirmationOpen && dialog.open) {
      dialog.close();
    }
  }, [paidFixConfirmationOpen]);

  const selectedDeploymentIsExact =
    Boolean(deployId) && currentDeployment?.id === deployId;
  const canRedeploy =
    selectedDeploymentIsExact &&
    currentDeployment != null &&
    terminalStatuses.has(currentDeployment.status);
  const isFailed = currentDeployment?.status === "failed";

  const safeLiveUrl = safeExternalUrl(currentDeployment?.live_url ?? null);
  const planRevision = metadataValue(
    currentDeployment?.infrastructure_metadata,
    ["architecture_plan", "revision"],
  );
  const worker = metadataValue(currentDeployment?.infrastructure_metadata, [
    "worker_id",
  ]);
  const targetProvider = metadataValue(
    currentDeployment?.infrastructure_metadata,
    ["target_provider"],
  );
  const activeProjectId =
    requestedProjectId || currentDeployment?.project_id || null;
  const visibleHistory = activeProjectId
    ? history.filter(
        (deployment) => deployment.project_id === activeProjectId,
      )
    : history;
  const deploymentHistoryHref = activeProjectId
    ? `/dashboard/deployments?${new URLSearchParams({
        project: activeProjectId,
      }).toString()}`
    : "/dashboard/deployments";

  const handleRedeploy = async () => {
    if (
      !deployId ||
      !currentDeployment ||
      currentDeployment.id !== deployId ||
      !terminalStatuses.has(currentDeployment.status)
    ) {
      addToast(
        "Select and load the exact deployment you want to retry.",
        "error",
      );
      return;
    }

    setRedeploying(true);
    try {
      const data = await api.startDeployment({
        project_id: currentDeployment.project_id,
        branch: currentDeployment.branch,
        environment: currentDeployment.environment,
      });
      const params = new URLSearchParams({ id: data.deployment_id });
      params.set("project", currentDeployment.project_id);
      if (currentDeployment.project_name) {
        params.set("repo", currentDeployment.project_name);
      }
      router.push(`/dashboard/deployments?${params.toString()}`);
    } catch (error) {
      addToast(
        getErrorMessage(error, "A new deployment could not be started."),
        "error",
      );
    } finally {
      setRedeploying(false);
    }
  };

  const handleCreateBillingRequest = async () => {
    if (
      !deployId ||
      !currentDeployment ||
      currentDeployment.id !== deployId ||
      currentDeployment.status !== "failed" ||
      requestingPaidFix
    ) {
      addToast(
        "Load the exact failed deployment before creating a remediation request.",
        "error",
      );
      return;
    }

    setRequestingPaidFix(true);
    try {
      await api.createBillingOperation({
        operation_type: "ai_code_fix",
        project_id: currentDeployment.project_id,
        deployment_id: currentDeployment.id,
        description:
          failureAnalysis?.recommended_fix ||
          `AI remediation request for failed deployment ${currentDeployment.id}`,
      });
      setPaidFixConfirmationOpen(false);
      addToast(
        "Billing request created. No payment or code change was completed.",
        "info",
      );
    } catch (error) {
      addToast(
        getErrorMessage(error, "The billing request could not be created."),
        "error",
      );
    } finally {
      setRequestingPaidFix(false);
    }
  };

  const handleCopyUrl = async () => {
    if (!currentDeployment?.live_url) return;
    try {
      await navigator.clipboard.writeText(currentDeployment.live_url);
      addToast("Recorded application URL copied.", "success");
    } catch {
      addToast("The application URL could not be copied.", "error");
    }
  };

  const handleCopyLogs = async () => {
    if (logLines.length === 0) return;
    const output = logLines
      .map(
        (line) =>
          `${line.lineNumber ?? "-"} [${logPrefix(line.type)}] ${line.text}`,
      )
      .join("\n");
    try {
      await navigator.clipboard.writeText(output);
      addToast("Deployment logs copied.", "success");
    } catch {
      addToast("The deployment logs could not be copied.", "error");
    }
  };

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Delivery"
        title="Deployment activity"
        description="Follow backend-recorded execution stages, inspect persisted and live logs, and review previous deployment runs."
        actions={
          <button
            type="button"
            onClick={() => void fetchHistory()}
            disabled={historyLoading}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3.5 text-xs font-semibold text-foreground shadow-sm transition-colors hover:bg-card-hover disabled:opacity-50"
          >
            <RefreshCw
              size={15}
              className={cn(
                historyLoading &&
                  "animate-spin motion-reduce:animate-none",
              )}
              aria-hidden="true"
            />
            Refresh history
          </button>
        }
      />

      {activeProjectId && <ProjectTabs projectId={activeProjectId} />}

      <section aria-labelledby="selected-deployment-heading">
        <div className="mb-4">
          <h2
            id="selected-deployment-heading"
            className="text-base font-semibold text-foreground"
          >
            Selected deployment
          </h2>
          <p className="mt-1 text-xs leading-5 text-foreground-muted">
            Retry and remediation actions are bound to this exact deployment
            record.
          </p>
        </div>

        {!deployId ? (
          <StatePanel
            variant="info"
            title="Select a deployment"
            description="Choose a deployment from history to inspect its recorded stages, diagnostics, and logs."
          />
        ) : selectedLoading && !currentDeployment ? (
          <div
            aria-label="Loading selected deployment"
            className="space-y-4 rounded-xl border border-border bg-card p-5"
          >
            <div className="h-7 w-52 animate-pulse rounded bg-surface-raised motion-reduce:animate-none" />
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[0, 1, 2, 3].map((item) => (
                <div
                  key={item}
                  className="h-20 animate-pulse rounded-lg bg-surface-subtle motion-reduce:animate-none"
                />
              ))}
            </div>
          </div>
        ) : selectedError || !currentDeployment ? (
          <StatePanel
            variant="error"
            title="Deployment unavailable"
            description={
              selectedError ||
              "The selected deployment record is not available to this account."
            }
            action={{
              label: "Return to deployment history",
              href: deploymentHistoryHref,
            }}
          />
        ) : (
          <div className="space-y-5">
            <article className="rounded-xl border border-border bg-card shadow-sm">
              <div className="flex flex-col gap-4 border-b border-border px-4 py-5 sm:px-5 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="break-words text-lg font-semibold text-foreground">
                      {currentDeployment.project_name || "Unnamed project"}
                    </h3>
                    <StatusBadge status={currentDeployment.status} />
                  </div>
                  <p className="mt-2 text-sm leading-6 text-foreground-muted">
                    {statusDescription(currentDeployment.status)}
                  </p>
                  <p className="mt-1 break-all font-mono text-[11px] text-foreground-subtle">
                    {currentDeployment.id}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {streamState === "unavailable" && (
                    <button
                      type="button"
                      onClick={() => void refreshSelectedDeployment()}
                      disabled={selectedLoading}
                      className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3.5 text-xs font-semibold text-foreground transition-colors hover:bg-card-hover disabled:opacity-50"
                    >
                      <RefreshCw
                        size={14}
                        className={cn(
                          selectedLoading &&
                            "animate-spin motion-reduce:animate-none",
                        )}
                        aria-hidden="true"
                      />
                      Refresh record
                    </button>
                  )}
                  {canRedeploy && (
                    <button
                      type="button"
                      onClick={() => void handleRedeploy()}
                      disabled={redeploying}
                      className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-primary px-3.5 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-primary-hover disabled:opacity-50"
                    >
                      {redeploying ? (
                        <Loader2
                          size={14}
                          className="animate-spin motion-reduce:animate-none"
                          aria-hidden="true"
                        />
                      ) : (
                        <RotateCcw size={14} aria-hidden="true" />
                      )}
                      {redeploying
                        ? "Starting new deployment"
                        : isFailed
                          ? "Retry as new deployment"
                          : "Redeploy as new deployment"}
                    </button>
                  )}
                </div>
              </div>

              <dl className="grid gap-px bg-border sm:grid-cols-2 lg:grid-cols-4">
                {[
                  ["Version", currentDeployment.version || "Not recorded"],
                  ["Commit", shortCommit(currentDeployment.commit_sha)],
                  ["Branch", currentDeployment.branch || "Not recorded"],
                  ["Environment", currentDeployment.environment],
                  ["Started", formatDateTime(currentDeployment.started_at)],
                  ["Completed", formatDateTime(currentDeployment.completed_at)],
                  ["Duration", deploymentDuration(currentDeployment)],
                  ["Triggered by", currentDeployment.deployed_by || "Not recorded"],
                  ["Plan revision", planRevision || "Not recorded"],
                  ["Target provider", targetProvider || "Not recorded"],
                  ["Execution worker", worker || "Not provided by API"],
                  ["Cost impact", "Not provided by API"],
                ].map(([label, value]) => (
                  <div key={label} className="min-w-0 bg-card px-4 py-3.5">
                    <dt className="text-[11px] font-semibold uppercase tracking-[0.08em] text-foreground-subtle">
                      {label}
                    </dt>
                    <dd
                      className={cn(
                        "mt-1 break-words text-sm text-foreground",
                        (label === "Commit" || label === "Branch") &&
                          "font-mono text-xs",
                      )}
                      title={label === "Commit" ? currentDeployment.commit_sha ?? undefined : undefined}
                    >
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>

              <div className="flex flex-col gap-3 border-t border-border px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-foreground">
                    Recorded application URL
                  </p>
                  <p className="mt-1 break-all font-mono text-xs text-foreground-muted">
                    {currentDeployment.live_url || "Not recorded"}
                  </p>
                  {currentDeployment.live_url && !safeLiveUrl && (
                    <p className="mt-1 text-xs text-warning">
                      This value is not a valid HTTP(S) URL, so it cannot be
                      opened from this page.
                    </p>
                  )}
                </div>
                {safeLiveUrl && (
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void handleCopyUrl()}
                      className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground transition-colors hover:bg-card-hover"
                    >
                      <Copy size={14} aria-hidden="true" />
                      Copy URL
                    </button>
                    <a
                      href={safeLiveUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground transition-colors hover:bg-card-hover"
                    >
                      <ExternalLink size={14} aria-hidden="true" />
                      Open application
                    </a>
                    <Link
                      href={`/dashboard/monitoring?project=${currentDeployment.project_id}`}
                      className="inline-flex min-h-11 items-center rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground transition-colors hover:bg-card-hover"
                    >
                      Open monitoring
                    </Link>
                  </div>
                )}
              </div>
            </article>

            {isFailed && (
              <section
                aria-labelledby="failure-analysis-heading"
                className="rounded-xl border border-danger/25 bg-danger-subtle"
              >
                <div className="flex items-start gap-3 border-b border-danger/20 px-4 py-4 sm:px-5">
                  <AlertCircle
                    size={20}
                    className="mt-0.5 shrink-0 text-danger"
                    aria-hidden="true"
                  />
                  <div>
                    <h3
                      id="failure-analysis-heading"
                      className="text-sm font-semibold text-foreground"
                    >
                      Failure diagnostics
                    </h3>
                    <p className="mt-1 text-xs leading-5 text-foreground-muted">
                      Review the recorded analysis and raw deployment logs before
                      starting another run.
                    </p>
                  </div>
                </div>

                <div className="px-4 py-5 sm:px-5">
                  {failureAnalysisLoading ? (
                    <div
                      role="status"
                      className="flex min-h-24 items-center justify-center gap-2 text-sm text-foreground-muted"
                    >
                      <Loader2
                        size={18}
                        className="animate-spin text-primary motion-reduce:animate-none"
                        aria-hidden="true"
                      />
                      Loading recorded failure analysis
                    </div>
                  ) : failureAnalysis ? (
                    <div className="space-y-5">
                      <dl className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                        <div>
                          <dt className="text-xs font-semibold text-foreground">
                            What happened
                          </dt>
                          <dd className="mt-1.5 text-sm leading-6 text-foreground-muted">
                            {failureAnalysis.failure_summary}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-xs font-semibold text-foreground">
                            Analyzer hypothesis
                          </dt>
                          <dd className="mt-1.5 text-sm leading-6 text-foreground-muted">
                            {failureAnalysis.root_cause}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-xs font-semibold text-foreground">
                            Recommended fix
                          </dt>
                          <dd className="mt-1.5 text-sm leading-6 text-foreground-muted">
                            {failureAnalysis.recommended_fix}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-xs font-semibold text-foreground">
                            Severity
                          </dt>
                          <dd className="mt-1.5 text-sm text-foreground-muted">
                            {failureAnalysis.severity || "Not provided"}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-xs font-semibold text-foreground">
                            Analyzer-noted impact
                          </dt>
                          <dd className="mt-1.5 text-sm text-foreground-muted">
                            {failureAnalysis.impact || "Not provided"}
                          </dd>
                        </div>
                      </dl>

                      {failureAnalysis.step_by_step_resolution.length > 0 && (
                        <div className="border-t border-danger/20 pt-4">
                          <button
                            type="button"
                            aria-expanded={resolutionOpen}
                            aria-controls="failure-resolution-steps"
                            onClick={() =>
                              setResolutionOpen((current) => !current)
                            }
                            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-danger/25 bg-card px-3 text-xs font-semibold text-foreground transition-colors hover:bg-card-hover"
                          >
                            {resolutionOpen
                              ? "Hide resolution steps"
                              : "Show resolution steps"}
                            {resolutionOpen ? (
                              <ChevronUp size={15} aria-hidden="true" />
                            ) : (
                              <ChevronDown size={15} aria-hidden="true" />
                            )}
                          </button>
                          {resolutionOpen && (
                            <ol
                              id="failure-resolution-steps"
                              className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-6 text-foreground-muted"
                            >
                              {failureAnalysis.step_by_step_resolution.map(
                                (step, index) => (
                                  <li key={`${index}-${step}`}>{step}</li>
                                ),
                              )}
                            </ol>
                          )}
                        </div>
                      )}
                    </div>
                  ) : (
                    <p role="status" className="text-sm text-foreground-muted">
                      {failureAnalysisError ||
                        "No failure analysis was returned for this deployment."}
                    </p>
                  )}
                </div>

                <div className="flex flex-col gap-3 border-t border-danger/20 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
                  <p className="max-w-2xl text-xs leading-5 text-foreground-muted">
                    Paid remediation pricing is not available before a billing
                    request is created. Creating a request does not purchase or
                    apply a fix.
                  </p>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <a
                      href="#deployment-logs"
                      className="inline-flex min-h-11 items-center rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground transition-colors hover:bg-card-hover"
                    >
                      View logs
                    </a>
                    <button
                      type="button"
                      onClick={() => setPaidFixConfirmationOpen(true)}
                      disabled={!selectedDeploymentIsExact}
                      className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-primary px-3.5 text-xs font-semibold text-white transition-colors hover:bg-primary-hover disabled:opacity-50"
                    >
                      <ServerCog size={14} aria-hidden="true" />
                      Create remediation billing request
                    </button>
                  </div>
                </div>
              </section>
            )}

            <StageTimeline
              stages={stages}
              deploymentStatus={currentDeployment.status}
            />

            <DeploymentLogs
              lines={logLines}
              open={logsOpen}
              onToggle={() => setLogsOpen((current) => !current)}
              onCopy={() => void handleCopyLogs()}
              streamState={streamState}
            />
          </div>
        )}
      </section>

      <section
        aria-labelledby="deployment-history-heading"
        className="rounded-xl border border-border bg-card shadow-sm"
      >
        <div className="flex flex-col gap-2 border-b border-border px-4 py-4 sm:flex-row sm:items-end sm:justify-between sm:px-5">
          <div>
            <h2
              id="deployment-history-heading"
              className="text-base font-semibold text-foreground"
            >
              Deployment history
            </h2>
            <p className="mt-1 text-xs leading-5 text-foreground-muted">
              {activeProjectId
                ? "Recent deployment records for the selected project."
                : "The 20 most recent deployment records returned by the backend."}
            </p>
          </div>
          <p className="text-xs text-foreground-subtle">
            Worker identity, cost impact, and rollback availability are not
            exposed by this API.
          </p>
        </div>

        <div className="p-4 sm:p-5">
          {historyLoading ? (
            <HistorySkeleton />
          ) : historyError && visibleHistory.length === 0 ? (
            <StatePanel
              compact
              variant="error"
              title="Deployment history unavailable"
              description={historyError}
              action={{
                label: "Try again",
                onClick: () => void fetchHistory(),
              }}
            />
          ) : visibleHistory.length === 0 ? (
            <StatePanel
              compact
              title={
                activeProjectId
                  ? "No recent deployments for this project"
                  : "No deployments yet"
              }
              description={
                activeProjectId
                  ? "No matching records were returned in the latest deployment history."
                  : "Deployment records will appear here after a project is queued for deployment."
              }
              action={{
                label: activeProjectId
                  ? "Open project overview"
                  : "Review repositories",
                href: activeProjectId
                  ? `/dashboard/apps/${activeProjectId}`
                  : "/dashboard/repositories",
              }}
            />
          ) : (
            <>
              {historyError && (
                <div
                  role="status"
                  className="mb-4 rounded-lg border border-warning/25 bg-warning-subtle px-3 py-2 text-xs text-foreground"
                >
                  Refresh failed. Showing the most recently loaded deployment
                  history.
                </div>
              )}

              <div className="grid gap-3 md:hidden">
                {visibleHistory.map((deployment) => (
                  <Link
                    key={deployment.id}
                    href={deploymentHref(deployment)}
                    aria-current={deployment.id === deployId ? "page" : undefined}
                    className={cn(
                      "rounded-lg border bg-card p-4 transition-colors hover:bg-card-hover",
                      deployment.id === deployId
                        ? "border-primary"
                        : "border-border",
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="break-words text-sm font-semibold text-foreground">
                          {deployment.project_name || "Unnamed project"}
                        </p>
                        <p className="mt-1 font-mono text-xs text-foreground-muted">
                          {deployment.version || "Version not recorded"}
                        </p>
                      </div>
                      <StatusBadge
                        status={deployment.status}
                        className="shrink-0"
                      />
                    </div>
                    <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3">
                      <div>
                        <dt className="text-[11px] text-foreground-subtle">
                          Environment
                        </dt>
                        <dd className="mt-0.5 text-xs text-foreground">
                          {deployment.environment}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-[11px] text-foreground-subtle">
                          Branch
                        </dt>
                        <dd className="mt-0.5 break-words font-mono text-xs text-foreground">
                          {deployment.branch || "Not recorded"}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-[11px] text-foreground-subtle">
                          Started
                        </dt>
                        <dd className="mt-0.5 text-xs text-foreground">
                          {formatDateTime(deployment.started_at)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-[11px] text-foreground-subtle">
                          Duration
                        </dt>
                        <dd className="mt-0.5 text-xs text-foreground">
                          {deploymentDuration(deployment)}
                        </dd>
                      </div>
                      <div className="col-span-2">
                        <dt className="text-[11px] text-foreground-subtle">
                          Commit
                        </dt>
                        <dd className="mt-0.5 break-all font-mono text-xs text-foreground">
                          {shortCommit(deployment.commit_sha)}
                        </dd>
                      </div>
                    </dl>
                  </Link>
                ))}
              </div>

              <div className="hidden overflow-x-auto md:block">
                <table className="w-full min-w-[920px] text-left text-xs">
                  <caption className="sr-only">
                    Recent deployment records
                  </caption>
                  <thead>
                    <tr className="border-b border-border text-foreground-subtle">
                      <th scope="col" className="px-3 py-3 font-semibold">
                        Project
                      </th>
                      <th scope="col" className="px-3 py-3 font-semibold">
                        Version / commit
                      </th>
                      <th scope="col" className="px-3 py-3 font-semibold">
                        Branch
                      </th>
                      <th scope="col" className="px-3 py-3 font-semibold">
                        Environment
                      </th>
                      <th scope="col" className="px-3 py-3 font-semibold">
                        Status
                      </th>
                      <th scope="col" className="px-3 py-3 font-semibold">
                        Started
                      </th>
                      <th scope="col" className="px-3 py-3 font-semibold">
                        Duration
                      </th>
                      <th scope="col" className="px-3 py-3 font-semibold">
                        Triggered by
                      </th>
                      <th scope="col" className="px-3 py-3 text-right font-semibold">
                        Details
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleHistory.map((deployment) => (
                      <tr
                        key={deployment.id}
                        className={cn(
                          "border-b border-border/70 last:border-0",
                          deployment.id === deployId && "bg-primary-subtle/50",
                        )}
                      >
                        <th
                          scope="row"
                          className="max-w-52 px-3 py-3 font-semibold text-foreground"
                        >
                          <span className="block break-words">
                            {deployment.project_name || "Unnamed project"}
                          </span>
                        </th>
                        <td className="px-3 py-3">
                          <span className="block font-mono text-foreground">
                            {deployment.version || "Not recorded"}
                          </span>
                          <span
                            className="mt-0.5 block font-mono text-foreground-subtle"
                            title={deployment.commit_sha ?? undefined}
                          >
                            {shortCommit(deployment.commit_sha)}
                          </span>
                        </td>
                        <td className="max-w-40 px-3 py-3 font-mono text-foreground-muted">
                          <span className="block break-words">
                            {deployment.branch || "Not recorded"}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-foreground-muted">
                          {deployment.environment}
                        </td>
                        <td className="px-3 py-3">
                          <StatusBadge status={deployment.status} />
                        </td>
                        <td className="px-3 py-3 text-foreground-muted">
                          {formatDateTime(deployment.started_at)}
                        </td>
                        <td className="px-3 py-3 text-foreground-muted">
                          {deploymentDuration(deployment)}
                        </td>
                        <td className="px-3 py-3 text-foreground-muted">
                          {deployment.deployed_by || "Not recorded"}
                        </td>
                        <td className="px-3 py-3 text-right">
                          <Link
                            href={deploymentHref(deployment)}
                            aria-label={`View deployment ${deployment.version || deployment.id} for ${deployment.project_name || "unnamed project"}`}
                            className="inline-flex min-h-11 items-center rounded-lg border border-border bg-card px-3 font-semibold text-foreground transition-colors hover:bg-card-hover"
                          >
                            View
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </section>

      <dialog
        ref={paidFixDialogRef}
        aria-labelledby="paid-fix-dialog-title"
        aria-describedby="paid-fix-dialog-description"
        onCancel={() => setPaidFixConfirmationOpen(false)}
        onClose={() => setPaidFixConfirmationOpen(false)}
        className="m-auto w-[calc(100%_-_2rem)] max-w-lg rounded-xl border border-border bg-card p-0 text-foreground shadow-2xl backdrop:bg-slate-950/60"
      >
        <div className="border-b border-border px-5 py-4">
          <h2
            id="paid-fix-dialog-title"
            className="text-base font-semibold text-foreground"
          >
            Create a remediation billing request?
          </h2>
        </div>
        <div className="space-y-4 px-5 py-5">
          <div
            id="paid-fix-dialog-description"
            className="space-y-3 text-sm leading-6 text-foreground-muted"
          >
            <p>
              The configured remediation price is not available through a
              pricing endpoint before this request is created.
            </p>
            <p>
              This action creates a billing request for deployment{" "}
              <span className="break-all font-mono text-xs text-foreground">
                {currentDeployment?.id}
              </span>
              . It does not charge you, complete a purchase, or apply any code
              change.
            </p>
            <p>
              Review any returned amount and checkout information separately in
              Billing before payment.
            </p>
          </div>
          <div className="rounded-lg border border-warning/25 bg-warning-subtle px-3 py-3 text-xs leading-5 text-foreground">
            No remediation worker will run from this confirmation.
          </div>
        </div>
        <div className="flex flex-col-reverse gap-2 border-t border-border px-5 py-4 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={() => setPaidFixConfirmationOpen(false)}
            disabled={requestingPaidFix}
            className="inline-flex min-h-11 items-center justify-center rounded-lg border border-border bg-card px-4 text-xs font-semibold text-foreground transition-colors hover:bg-card-hover disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void handleCreateBillingRequest()}
            disabled={requestingPaidFix}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary px-4 text-xs font-semibold text-white transition-colors hover:bg-primary-hover disabled:opacity-50"
          >
            {requestingPaidFix && (
              <Loader2
                size={14}
                className="animate-spin motion-reduce:animate-none"
                aria-hidden="true"
              />
            )}
            {requestingPaidFix
              ? "Creating billing request"
              : "Create billing request"}
          </button>
        </div>
      </dialog>
    </div>
  );
}

export default function DeploymentsPage() {
  return (
    <Suspense
      fallback={
        <div
          role="status"
          className="flex min-h-[24rem] items-center justify-center gap-2 text-sm text-foreground-muted"
        >
          <Loader2
            size={22}
            className="animate-spin text-primary motion-reduce:animate-none"
            aria-hidden="true"
          />
          Loading deployment activity
        </div>
      }
    >
      <DeploymentsPageContent />
    </Suspense>
  );
}
