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
  ChevronDown,
  ChevronUp,
  Copy,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCw,
  RotateCcw,
  ServerCog,
  ShieldCheck,
  Wifi,
  WifiOff,
  XCircle,
} from "lucide-react";
import { PipelineTimeline } from "@/components/dashboard/pipeline/PipelineTimeline";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ProjectTabs } from "@/components/dashboard/ProjectTabs";
import {
  ApiError,
  api,
  type Deployment,
  type DeploymentDetail,
  type FailureAnalysis,
  type PipelineEvidence,
  type PipelineRun,
  type PipelineStageAttempt,
  type PipelineStageStatus,
} from "@/lib/api";
import { useNotifications } from "@/lib/NotificationContext";
import { createReconnectingWebSocket } from "@/lib/runtime-config";
import { cn } from "@/lib/utils";

type LegacyStageStatus = "pending" | "active" | "completed";

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

type PipelineLoadState = "idle" | "available" | "no_record" | "unavailable" | "error";

interface DeploymentStreamEvent {
  type?: unknown;
  id?: unknown;
  label?: unknown;
  status?: unknown;
  duration?: unknown;
  text?: unknown;
  lineType?: unknown;
  line_number?: unknown;
  stage_key?: unknown;
  name?: unknown;
  order?: unknown;
  attempt?: unknown;
  required?: unknown;
  tool?: unknown;
  reason?: unknown;
  summary?: unknown;
  evidence?: unknown;
  started_at?: unknown;
  completed_at?: unknown;
  duration_seconds?: unknown;
  logs_available?: unknown;
  log_count?: unknown;
  ai_used?: unknown;
  approval_required?: unknown;
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

function isStageStatus(
  value: unknown,
): value is PipelineStageStatus | LegacyStageStatus {
  return (
    value === "pending" ||
    value === "active" ||
    value === "completed" ||
    value === "queued" ||
    value === "running" ||
    value === "succeeded" ||
    value === "failed" ||
    value === "skipped" ||
    value === "blocked" ||
    value === "unavailable" ||
    value === "cancelled"
  );
}

function normalizeStageStatus(
  status: PipelineStageStatus | LegacyStageStatus,
): PipelineStageStatus {
  if (status === "pending") return "queued";
  if (status === "active") return "running";
  if (status === "completed") return "succeeded";
  return status;
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

function parseDurationSeconds(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return null;
  const match = value.trim().match(/^(\d+(?:\.\d+)?)s$/);
  return match ? Number(match[1]) : null;
}

function parseEvidenceKind(value: unknown): PipelineEvidence["kind"] {
  if (
    value === "text" ||
    value === "commit" ||
    value === "artifact" ||
    value === "policy" ||
    value === "log" ||
    value === "url"
  ) {
    return value;
  }
  return undefined;
}

function parseRecordedStages(value: unknown): PipelineStageAttempt[] {
  if (!Array.isArray(value)) return [];

  return value.flatMap((item, index) => {
    if (!isRecord(item)) return [];
    const name =
      typeof item.name === "string" && item.name.trim()
        ? item.name.trim()
        : typeof item.label === "string" && item.label.trim()
          ? item.label.trim()
          : null;
    if (!name || !isStageStatus(item.status)) {
      return [];
    }

    const rawId = item.id;
    const id =
      typeof rawId === "string" || typeof rawId === "number"
        ? String(rawId)
        : `legacy-stage-${index + 1}`;
    const evidence = Array.isArray(item.evidence)
      ? item.evidence.flatMap((entry) => {
          if (!isRecord(entry) || typeof entry.label !== "string" || typeof entry.value !== "string") {
            return [];
          }
          return [{
            id: typeof entry.id === "string" ? entry.id : undefined,
            label: entry.label,
            value: entry.value,
            kind: parseEvidenceKind(entry.kind),
            url: typeof entry.url === "string" ? entry.url : null,
            sensitive: entry.sensitive === true,
          }];
        })
      : [];

    return [
      {
        id,
        stage_key:
          typeof item.stage_key === "string" && item.stage_key.trim()
            ? item.stage_key.trim()
            : id,
        name,
        description: typeof item.description === "string" ? item.description : null,
        status: normalizeStageStatus(item.status),
        order:
          typeof item.order === "number" && Number.isFinite(item.order)
            ? item.order
            : typeof rawId === "number" && Number.isFinite(rawId)
              ? rawId
              : index + 1,
        attempt:
          typeof item.attempt === "number" && Number.isFinite(item.attempt)
            ? item.attempt
            : 1,
        required: item.required !== false,
        tool: typeof item.tool === "string" ? item.tool : null,
        reason: typeof item.reason === "string" ? item.reason : null,
        summary: typeof item.summary === "string" ? item.summary : null,
        evidence,
        started_at: typeof item.started_at === "string" ? item.started_at : null,
        completed_at: typeof item.completed_at === "string" ? item.completed_at : null,
        duration_seconds: parseDurationSeconds(item.duration_seconds ?? item.duration),
        duration_label: typeof item.duration === "string" ? item.duration.trim() : null,
        logs_available: item.logs_available === true,
        log_count: typeof item.log_count === "number" ? item.log_count : 0,
        ai_used: item.ai_used === true,
        approval_required: item.approval_required === true,
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
      className="ops-surface overflow-hidden"
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
  const [stages, setStages] = useState<PipelineStageAttempt[]>([]);
  const [pipelineRun, setPipelineRun] = useState<PipelineRun | null>(null);
  const [pipelineLoadState, setPipelineLoadState] =
    useState<PipelineLoadState>("idle");
  const [pipelineLoadMessage, setPipelineLoadMessage] = useState<string | null>(null);
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
  const [approvalAction, setApprovalAction] = useState<
    "approve" | "reject" | null
  >(null);
  const [approvalActionError, setApprovalActionError] = useState<string | null>(
    null,
  );
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

  const applyPipelineError = useCallback((error: unknown) => {
    setPipelineRun(null);
    if (error instanceof ApiError && error.status === 404) {
      setPipelineLoadState("no_record");
      setPipelineLoadMessage(
        "No pipeline run is stored for this deployment. Legacy stage metadata is shown when available.",
      );
      return;
    }
    if (error instanceof ApiError && error.status === 503) {
      setPipelineLoadState("unavailable");
      setPipelineLoadMessage(
        "The pipeline service is unavailable. No stage result has been inferred from that outage.",
      );
      return;
    }
    setPipelineLoadState("error");
    setPipelineLoadMessage(
      getErrorMessage(error, "The recorded pipeline could not be loaded."),
    );
  }, []);

  const refreshSelectedDeployment = useCallback(async () => {
    if (!deployId) return;
    setSelectedLoading(true);
    setSelectedError(null);
    try {
      const [detail, pipeline] = await Promise.all([
        api.getDeployment(deployId),
        api.getDeploymentPipeline(deployId).catch((error: unknown) => {
          applyPipelineError(error);
          return null;
        }),
      ]);
      applyDeploymentDetail(detail);
      if (pipeline) {
        setPipelineRun(pipeline);
        setStages(pipeline.stages);
        setPipelineLoadState("available");
        setPipelineLoadMessage(null);
      }
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
  }, [applyDeploymentDetail, applyPipelineError, deployId]);

  useEffect(() => {
    void fetchHistory();
  }, [fetchHistory]);

  useEffect(() => {
    setPaidFixConfirmationOpen(false);
    setResolutionOpen(false);
    setFailureAnalysis(null);
    setFailureAnalysisError(null);
    setApprovalAction(null);
    setApprovalActionError(null);
    liveLogSequence.current = 0;

    if (!deployId) {
      setCurrentDeployment(null);
      setSelectedError(null);
      setSelectedLoading(false);
      setStages([]);
      setPipelineRun(null);
      setPipelineLoadState("idle");
      setPipelineLoadMessage(null);
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
    setPipelineRun(null);
    setPipelineLoadState("idle");
    setPipelineLoadMessage(null);
    setLogLines([]);
    setStreamState("idle");

    async function loadDeploymentAndStream() {
      const [detailResult, pipelineResult] = await Promise.allSettled([
        api.getDeployment(selectedDeploymentId),
        api.getDeploymentPipeline(selectedDeploymentId),
      ]);
      if (detailResult.status === "rejected") {
        if (!active) return;
        setSelectedError(
          getErrorMessage(
            detailResult.reason,
            "The selected deployment could not be loaded.",
          ),
        );
        setSelectedLoading(false);
        return;
      }

      if (!active) return;
      const detail = detailResult.value;
      applyDeploymentDetail(detail);
      if (pipelineResult.status === "fulfilled") {
        setPipelineRun(pipelineResult.value);
        setStages(pipelineResult.value.stages);
        setPipelineLoadState("available");
        setPipelineLoadMessage(null);
      } else {
        applyPipelineError(pipelineResult.reason);
      }
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

              const eventStageStatus = isStageStatus(data.status)
                ? normalizeStageStatus(data.status)
                : data.type === "pipeline_stage_started"
                  ? "running"
                  : data.type === "pipeline_stage_completed"
                    ? "succeeded"
                    : data.type === "pipeline_stage_failed"
                      ? "failed"
                      : null;
              const isPipelineStageEvent =
                data.type === "stage" ||
                (typeof data.type === "string" && data.type.startsWith("pipeline_stage_"));
              if (
                isPipelineStageEvent &&
                eventStageStatus
              ) {
                const eventStage = parseRecordedStages([
                  {
                    ...data,
                    id: data.id ?? data.stage_key,
                    name: data.name ?? data.label,
                    status: eventStageStatus,
                  },
                ])[0];
                if (!eventStage) {
                  const eventStageId =
                    typeof data.id === "string" || typeof data.id === "number"
                      ? String(data.id)
                      : typeof data.stage_key === "string"
                        ? data.stage_key
                        : null;
                  if (eventStageId) {
                    setStages((previous) =>
                      previous.map((stage) =>
                        stage.id === eventStageId || stage.stage_key === eventStageId
                          ? { ...stage, status: eventStageStatus }
                          : stage,
                      ),
                    );
                  }
                  return;
                }
                setStages((previous) => {
                  const existingIndex = previous.findIndex(
                    (stage) =>
                      stage.id === eventStage.id ||
                      stage.stage_key === eventStage.stage_key,
                  );
                  if (existingIndex === -1) {
                    return [...previous, eventStage];
                  }

                  return previous.map((stage, index) =>
                    index === existingIndex
                      ? {
                          ...stage,
                          ...eventStage,
                          id: stage.id,
                          stage_key: stage.stage_key,
                          name:
                            typeof data.name === "string" || typeof data.label === "string"
                              ? eventStage.name
                              : stage.name,
                          description: eventStage.description ?? stage.description,
                          order:
                            typeof data.order === "number" ? eventStage.order : stage.order,
                          attempt:
                            typeof data.attempt === "number" ? eventStage.attempt : stage.attempt,
                          required:
                            typeof data.required === "boolean"
                              ? eventStage.required
                              : stage.required,
                          tool: eventStage.tool ?? stage.tool,
                          reason: eventStage.reason ?? stage.reason,
                          summary: eventStage.summary ?? stage.summary,
                          evidence:
                            eventStage.evidence?.length
                              ? eventStage.evidence
                              : stage.evidence,
                          started_at: eventStage.started_at ?? stage.started_at,
                          completed_at: eventStage.completed_at ?? stage.completed_at,
                          duration_seconds:
                            eventStage.duration_seconds ?? stage.duration_seconds,
                          duration_label:
                            eventStage.duration_label ?? stage.duration_label,
                          logs_available:
                            data.logs_available === true
                              ? eventStage.logs_available
                              : stage.logs_available,
                          log_count:
                            typeof data.log_count === "number"
                              ? eventStage.log_count
                              : stage.log_count,
                          ai_used:
                            typeof data.ai_used === "boolean"
                              ? eventStage.ai_used
                              : stage.ai_used,
                          approval_required:
                            typeof data.approval_required === "boolean"
                              ? eventStage.approval_required
                              : stage.approval_required,
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
                          void api
                            .getDeploymentPipeline(selectedDeploymentId)
                            .then((pipeline) => {
                              if (!active) return;
                              setPipelineRun(pipeline);
                              setStages(pipeline.stages);
                              setPipelineLoadState("available");
                              setPipelineLoadMessage(null);
                            })
                            .catch(applyPipelineError);
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
    applyPipelineError,
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
  const approvalPending =
    selectedDeploymentIsExact &&
    pipelineRun?.approval_required === true &&
    pipelineRun.approval_status === "pending" &&
    pipelineRun.status === "blocked";
  const approvalConsumed =
    pipelineRun?.approval_status === "approved_consumed" &&
    Boolean(pipelineRun.approved_deployment_id);
  const approvalRejected = pipelineRun?.approval_status === "rejected";

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

  const handlePipelineApproval = async () => {
    if (!pipelineRun || !approvalPending || approvalAction) return;

    setApprovalAction("approve");
    setApprovalActionError(null);
    try {
      const result = await api.approvePipelineRun(pipelineRun.id);
      addToast(
        result.idempotent
          ? "This approval was already recorded; opening its fresh execution."
          : "Approval recorded. A fresh execution was queued against the same immutable source.",
        "success",
      );
      const params = new URLSearchParams({ id: result.deployment_id });
      params.set("project", pipelineRun.project_id);
      if (currentDeployment?.project_name) {
        params.set("repo", currentDeployment.project_name);
      }
      router.push(`/dashboard/deployments?${params.toString()}`);
    } catch (error) {
      const message = getErrorMessage(
        error,
        "The deployment approval could not be recorded.",
      );
      setApprovalActionError(message);
      addToast(message, "error");
    } finally {
      setApprovalAction(null);
    }
  };

  const handlePipelineRejection = async () => {
    if (!pipelineRun || !approvalPending || approvalAction) return;

    setApprovalAction("reject");
    setApprovalActionError(null);
    try {
      await api.rejectPipelineRun(pipelineRun.id);
      addToast("The validated release was rejected and will not deploy.", "warning");
      await Promise.all([refreshSelectedDeployment(), fetchHistory(false)]);
      refreshStats();
    } catch (error) {
      const message = getErrorMessage(
        error,
        "The deployment rejection could not be recorded.",
      );
      setApprovalActionError(message);
      addToast(message, "error");
    } finally {
      setApprovalAction(null);
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
    <div className="space-y-7">
      <PageHeader
        eyebrow="Delivery"
        title="Deployment activity"
        description="Follow backend-recorded execution stages, inspect persisted and live logs, and review previous deployment runs."
        actions={
          <button
            type="button"
            onClick={() => void fetchHistory()}
            disabled={historyLoading}
            className="ops-secondary disabled:opacity-50"
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
        <SectionHeader
          id="selected-deployment-heading"
          eyebrow="Release record"
          title="Selected deployment"
          description="Retry, approval, and remediation actions stay bound to this exact deployment record. Missing evidence remains visibly unavailable."
          className="mb-4"
        />

        {!deployId ? (
          <StatePanel
            variant="info"
            title="Select a deployment"
            description="Choose a deployment from history to inspect its recorded stages, diagnostics, and logs."
          />
        ) : selectedLoading && !currentDeployment ? (
          <div
            aria-label="Loading selected deployment"
            className="ops-surface space-y-4 p-5"
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
            <article className="ops-surface overflow-hidden">
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
                  <p className="mt-1 break-all font-mono text-xs text-foreground-subtle">
                    {currentDeployment.id}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {streamState === "unavailable" && (
                    <button
                      type="button"
                      onClick={() => void refreshSelectedDeployment()}
                      disabled={selectedLoading}
                      className="ops-secondary disabled:opacity-50"
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
                      className="ops-primary disabled:opacity-50"
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
                    <dt className="text-xs font-semibold uppercase tracking-[0.08em] text-foreground-subtle">
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
                      className="ops-secondary"
                    >
                      <Copy size={14} aria-hidden="true" />
                      Copy URL
                    </button>
                    <a
                      href={safeLiveUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ops-secondary"
                    >
                      <ExternalLink size={14} aria-hidden="true" />
                      Open application
                    </a>
                    <Link
                      href={`/dashboard/monitoring?project=${currentDeployment.project_id}`}
                      className="ops-secondary"
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
                className="overflow-hidden rounded-2xl border border-danger/25 bg-card shadow-sm"
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
                      className="ops-primary disabled:opacity-50"
                    >
                      <ServerCog size={14} aria-hidden="true" />
                      Create remediation billing request
                    </button>
                  </div>
                </div>
              </section>
            )}

            {(approvalPending || approvalConsumed || approvalRejected) && (
              <section
                aria-labelledby="pipeline-approval-heading"
                className={cn(
                  "overflow-hidden rounded-2xl border bg-card shadow-sm",
                  approvalPending
                    ? "border-warning/35"
                    : approvalRejected
                      ? "border-danger/30"
                      : "border-success/30",
                )}
              >
                <div className="flex flex-col gap-4 px-4 py-4 sm:px-5 lg:flex-row lg:items-center lg:justify-between">
                  <div className="flex min-w-0 items-start gap-3">
                    {approvalRejected ? (
                      <XCircle
                        size={20}
                        className="mt-0.5 shrink-0 text-danger"
                        aria-hidden="true"
                      />
                    ) : (
                      <ShieldCheck
                        size={20}
                        className={cn(
                          "mt-0.5 shrink-0",
                          approvalPending ? "text-warning-hover" : "text-success",
                        )}
                        aria-hidden="true"
                      />
                    )}
                    <div>
                      <h3
                        id="pipeline-approval-heading"
                        className="text-sm font-semibold text-foreground"
                      >
                        {approvalPending
                          ? "Production deployment approval required"
                          : approvalRejected
                            ? "Production deployment rejected"
                            : "Approval recorded in a fresh execution"}
                      </h3>
                      <p className="mt-1 max-w-3xl text-xs leading-5 text-foreground-muted">
                        {approvalPending
                          ? "The immutable revision completed every required pre-deployment check and stopped at the approval gate. Approval creates a new run pinned to the same source, plan, target, and configuration, then reruns deterministic checks before deployment."
                          : approvalRejected
                            ? "The authenticated project owner rejected this validated release. No deployment job will resume from this approval gate."
                            : "This validation run was consumed by an authenticated approval. Deployment continues in a separate run so checks cannot be bypassed or resumed from a stale workspace."}
                      </p>
                      {approvalActionError && (
                        <p className="mt-2 text-xs text-danger" role="alert">
                          {approvalActionError}
                        </p>
                      )}
                    </div>
                  </div>

                  {approvalPending ? (
                    <div className="flex shrink-0 flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => void handlePipelineRejection()}
                        disabled={approvalAction !== null}
                        className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-danger/30 bg-card px-3.5 text-xs font-semibold text-danger transition-colors hover:bg-danger-subtle disabled:opacity-50"
                      >
                        {approvalAction === "reject" ? (
                          <Loader2
                            size={14}
                            className="animate-spin motion-reduce:animate-none"
                            aria-hidden="true"
                          />
                        ) : (
                          <XCircle size={14} aria-hidden="true" />
                        )}
                        Reject release
                      </button>
                      <button
                        type="button"
                        onClick={() => void handlePipelineApproval()}
                        disabled={approvalAction !== null}
                        className="ops-primary disabled:opacity-50"
                      >
                        {approvalAction === "approve" ? (
                          <Loader2
                            size={14}
                            className="animate-spin motion-reduce:animate-none"
                            aria-hidden="true"
                          />
                        ) : (
                          <ShieldCheck size={14} aria-hidden="true" />
                        )}
                        Approve and queue fresh run
                      </button>
                    </div>
                  ) : approvalConsumed && pipelineRun?.approved_deployment_id ? (
                    <Link
                      href={`/dashboard/deployments?${new URLSearchParams({
                        id: pipelineRun.approved_deployment_id,
                        project: pipelineRun.project_id,
                      }).toString()}`}
                      className="inline-flex min-h-11 shrink-0 items-center rounded-lg border border-border bg-card px-3.5 text-xs font-semibold text-foreground transition-colors hover:bg-card-hover"
                    >
                      Open approved execution
                    </Link>
                  ) : null}
                </div>
              </section>
            )}

            <PipelineTimeline
              stages={stages}
              runStatus={pipelineRun?.status}
              sourceMessage={pipelineLoadMessage ?? pipelineRun?.reason}
              emptyTitle={
                pipelineLoadState === "no_record"
                  ? "No pipeline run is stored"
                  : pipelineLoadState === "unavailable"
                    ? "Pipeline service unavailable"
                    : inProgressStatuses.has(currentDeployment.status)
                      ? "Pipeline stages are pending"
                      : "Pipeline stages are not recorded"
              }
              emptyDescription={
                pipelineLoadState === "no_record"
                  ? "This deployment predates, or does not have, a pipeline run record. No stages have been inferred."
                  : pipelineLoadState === "unavailable"
                    ? "The stage service could not provide a result. This is not a passed pipeline."
                    : "ZeroOps has not received stage attempts for this deployment."
              }
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
        className="ops-surface overflow-hidden"
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
                        <dt className="text-xs text-foreground-subtle">
                          Environment
                        </dt>
                        <dd className="mt-0.5 text-xs text-foreground">
                          {deployment.environment}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-foreground-subtle">
                          Branch
                        </dt>
                        <dd className="mt-0.5 break-words font-mono text-xs text-foreground">
                          {deployment.branch || "Not recorded"}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-foreground-subtle">
                          Started
                        </dt>
                        <dd className="mt-0.5 text-xs text-foreground">
                          {formatDateTime(deployment.started_at)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-foreground-subtle">
                          Duration
                        </dt>
                        <dd className="mt-0.5 text-xs text-foreground">
                          {deploymentDuration(deployment)}
                        </dd>
                      </div>
                      <div className="col-span-2">
                        <dt className="text-xs text-foreground-subtle">
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
        className="m-auto w-[calc(100%_-_2rem)] max-w-lg rounded-2xl border border-border bg-card p-0 text-foreground shadow-2xl backdrop:bg-slate-950/60"
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
            className="ops-primary disabled:opacity-50"
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
