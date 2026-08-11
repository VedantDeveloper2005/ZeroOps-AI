import {
  Ban,
  CheckCircle2,
  ChevronDown,
  CircleDashed,
  CircleOff,
  Clock3,
  Info,
  Loader2,
  ShieldAlert,
  SkipForward,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { StatePanel } from "@/components/ui/StatePanel";
import type {
  PipelineRunStatus,
  PipelineStageAttempt,
  PipelineStageStatus,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type StagePresentation = {
  label: string;
  icon: LucideIcon;
  iconClassName: string;
  badgeClassName: string;
};

const terminalStageStatuses = new Set<PipelineStageStatus>([
  "succeeded",
  "failed",
  "skipped",
  "blocked",
  "unavailable",
  "cancelled",
]);

const stagePresentation: Record<PipelineStageStatus, StagePresentation> = {
  queued: {
    label: "Queued",
    icon: CircleDashed,
    iconClassName: "text-foreground-subtle",
    badgeClassName: "border-border bg-surface-subtle text-foreground-muted",
  },
  running: {
    label: "Running",
    icon: Loader2,
    iconClassName: "animate-spin text-info motion-reduce:animate-none",
    badgeClassName: "border-info/25 bg-info-subtle text-info",
  },
  succeeded: {
    label: "Passed",
    icon: CheckCircle2,
    iconClassName: "text-success",
    badgeClassName: "border-success/25 bg-success-subtle text-success",
  },
  failed: {
    label: "Failed",
    icon: XCircle,
    iconClassName: "text-danger",
    badgeClassName: "border-danger/25 bg-danger-subtle text-danger",
  },
  skipped: {
    label: "Skipped",
    icon: SkipForward,
    iconClassName: "text-foreground-muted",
    badgeClassName: "border-border bg-surface-subtle text-foreground-muted",
  },
  blocked: {
    label: "Blocked",
    icon: ShieldAlert,
    iconClassName: "text-warning",
    badgeClassName: "border-warning/25 bg-warning-subtle text-warning",
  },
  unavailable: {
    label: "Unavailable",
    icon: CircleOff,
    iconClassName: "text-warning",
    badgeClassName: "border-warning/25 bg-warning-subtle text-warning",
  },
  cancelled: {
    label: "Cancelled",
    icon: Ban,
    iconClassName: "text-foreground-muted",
    badgeClassName: "border-border bg-surface-subtle text-foreground-muted",
  },
};

function formatTimestamp(value: string | null | undefined) {
  if (!value) return "Not recorded";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(parsed);
}

function formatDuration(stage: PipelineStageAttempt) {
  if (stage.duration_seconds != null && Number.isFinite(stage.duration_seconds)) {
    if (stage.duration_seconds < 60) return `${stage.duration_seconds.toFixed(1)}s`;
    const minutes = Math.floor(stage.duration_seconds / 60);
    const seconds = Math.round(stage.duration_seconds % 60);
    return `${minutes}m ${seconds}s`;
  }

  if (stage.started_at && stage.completed_at) {
    const start = new Date(stage.started_at).getTime();
    const end = new Date(stage.completed_at).getTime();
    if (Number.isFinite(start) && Number.isFinite(end) && end >= start) {
      return `${Math.round((end - start) / 1000)}s`;
    }
  }

  if (stage.duration_label && stage.duration_label !== "...") {
    return stage.duration_label;
  }

  return stage.status === "running" ? "In progress" : "Not recorded";
}

function safeEvidenceUrl(value: string | null | undefined) {
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

export function PipelineTimeline({
  stages,
  runStatus,
  sourceMessage,
  emptyTitle = "Pipeline stages are not recorded",
  emptyDescription = "The deployment exists, but no stage attempts were returned. ZeroOps has not inferred a pipeline result.",
}: {
  stages: PipelineStageAttempt[];
  runStatus?: PipelineRunStatus | null;
  sourceMessage?: string | null;
  emptyTitle?: string;
  emptyDescription?: string;
}) {
  const orderedStages = [...stages].sort(
    (first, second) => first.order - second.order || first.attempt - second.attempt,
  );
  const resolvedStages = orderedStages.filter((stage) =>
    terminalStageStatuses.has(stage.status),
  ).length;
  const runningStage = orderedStages.find((stage) => stage.status === "running");
  const progress = orderedStages.length
    ? Math.round((resolvedStages / orderedStages.length) * 100)
    : 0;
  const hasFailure = orderedStages.some((stage) =>
    ["failed", "blocked", "unavailable"].includes(stage.status),
  );

  return (
    <section
      aria-labelledby="deployment-stages-heading"
      className="overflow-hidden rounded-xl border border-border bg-card shadow-sm"
    >
      <div className="border-b border-border px-4 py-4 sm:px-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3 id="deployment-stages-heading" className="text-sm font-semibold text-foreground">
              Pipeline timeline
            </h3>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-foreground-muted">
              Recorded attempts only. Expand a stage to inspect its tool, timing, reason, and saved evidence.
            </p>
          </div>
          {orderedStages.length > 0 && (
            <p className="shrink-0 text-xs font-medium tabular-nums text-foreground-muted">
              {resolvedStages} of {orderedStages.length} resolved
            </p>
          )}
        </div>

        {orderedStages.length > 0 && (
          <div className="mt-4" role="status" aria-live="polite">
            <div
              role="progressbar"
              aria-label="Recorded pipeline stage progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progress}
              aria-valuetext={`${resolvedStages} of ${orderedStages.length} stages reached a terminal state`}
              className="h-1.5 overflow-hidden rounded-full bg-surface-raised"
            >
              <div
                className={cn(
                  "h-full rounded-full motion-safe:transition-[width] motion-safe:duration-300",
                  hasFailure ? "bg-danger" : runStatus === "completed" ? "bg-success" : "bg-info",
                )}
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-foreground-muted">
              <span>
                {runningStage
                  ? `Running: ${runningStage.name}`
                  : runStatus
                    ? `Pipeline status: ${runStatus.replaceAll("_", " ")}`
                    : "No stage is currently recorded as running."}
              </span>
              <span className="font-mono tabular-nums">{progress}%</span>
            </div>
          </div>
        )}

        {sourceMessage && (
          <p className="mt-3 rounded-lg border border-warning/25 bg-warning-subtle px-3 py-2 text-xs leading-5 text-foreground-muted">
            {sourceMessage}
          </p>
        )}
      </div>

      {orderedStages.length === 0 ? (
        <div className="p-4 sm:p-5">
          <StatePanel compact title={emptyTitle} description={emptyDescription} />
        </div>
      ) : (
        <ol className="divide-y divide-border/70">
          {orderedStages.map((stage, index) => {
            const presentation = stagePresentation[stage.status];
            const StatusIcon = presentation.icon;
            const evidence = stage.evidence ?? [];
            const expandedByDefault = ["running", "failed", "blocked", "unavailable"].includes(
              stage.status,
            );

            return (
              <li key={`${stage.id}-${stage.attempt}-${index}`}>
                <details className="group" open={expandedByDefault}>
                  <summary className="flex min-h-16 cursor-pointer list-none items-center gap-3 px-4 py-3 outline-none transition-colors hover:bg-surface-subtle focus-visible:bg-surface-subtle sm:px-5 [&::-webkit-details-marker]:hidden">
                    <span
                      className={cn(
                        "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border",
                        presentation.badgeClassName,
                      )}
                    >
                      <StatusIcon size={18} className={presentation.iconClassName} aria-hidden="true" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="break-words text-sm font-semibold text-foreground">
                          {stage.name}
                        </span>
                        <span
                          className={cn(
                            "rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                            presentation.badgeClassName,
                          )}
                        >
                          {presentation.label}
                        </span>
                        {stage.ai_used && (
                          <span className="rounded-full border border-primary/25 bg-primary-subtle px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
                            AI used
                          </span>
                        )}
                      </span>
                      <span className="mt-1 block text-xs leading-5 text-foreground-muted">
                        {stage.summary || stage.reason || stage.description || "No result summary was recorded."}
                      </span>
                    </span>
                    <span className="hidden shrink-0 text-right sm:block">
                      <span className="block font-mono text-xs tabular-nums text-foreground">
                        {formatDuration(stage)}
                      </span>
                      <span className="mt-0.5 block text-[10px] text-foreground-subtle">
                        Attempt {stage.attempt}
                      </span>
                    </span>
                    <ChevronDown
                      size={16}
                      className="shrink-0 text-foreground-subtle transition-transform duration-200 group-open:rotate-180 motion-reduce:transition-none"
                      aria-hidden="true"
                    />
                  </summary>

                  <div className="border-t border-border/70 bg-surface-subtle px-4 py-4 sm:px-5 sm:pl-[4.5rem]">
                    <dl className="grid gap-3 text-xs sm:grid-cols-2 xl:grid-cols-4">
                      <div>
                        <dt className="text-foreground-subtle">Tool</dt>
                        <dd className="mt-1 font-medium text-foreground">
                          {stage.tool || "Not recorded"}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-foreground-subtle">Started</dt>
                        <dd className="mt-1 font-medium text-foreground">
                          {formatTimestamp(stage.started_at)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-foreground-subtle">Finished</dt>
                        <dd className="mt-1 font-medium text-foreground">
                          {formatTimestamp(stage.completed_at)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-foreground-subtle">Duration</dt>
                        <dd className="mt-1 font-mono font-medium tabular-nums text-foreground">
                          {formatDuration(stage)}
                        </dd>
                      </div>
                    </dl>

                    {stage.reason && (
                      <div className="mt-4 rounded-lg border border-border bg-card px-3 py-2.5">
                        <div className="flex items-start gap-2">
                          <Info size={14} className="mt-0.5 shrink-0 text-info" aria-hidden="true" />
                          <div>
                            <p className="text-[10px] font-semibold uppercase tracking-wide text-foreground-subtle">
                              Decision reason
                            </p>
                            <p className="mt-1 text-xs leading-5 text-foreground-muted">
                              {stage.reason}
                            </p>
                          </div>
                        </div>
                      </div>
                    )}

                    <div className="mt-4">
                      <div className="flex items-center gap-2">
                        <Clock3 size={14} className="text-foreground-subtle" aria-hidden="true" />
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-foreground-subtle">
                          Evidence
                        </p>
                      </div>
                      {evidence.length === 0 ? (
                        <p className="mt-2 text-xs text-foreground-muted">
                          No stage evidence was stored.
                        </p>
                      ) : (
                        <ul className="mt-2 grid gap-2 lg:grid-cols-2">
                          {evidence.map((item, evidenceIndex) => {
                            const href = safeEvidenceUrl(item.url);
                            return (
                              <li
                                key={item.id ?? `${item.label}-${evidenceIndex}`}
                                className="rounded-lg border border-border bg-card px-3 py-2.5 text-xs"
                              >
                                <p className="font-medium text-foreground">{item.label}</p>
                                {item.sensitive ? (
                                  <p className="mt-1 text-foreground-muted">Sensitive value redacted</p>
                                ) : href ? (
                                  <a
                                    href={href}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="mt-1 inline-block break-all text-primary underline-offset-2 hover:underline"
                                  >
                                    {item.value}
                                  </a>
                                ) : (
                                  <p className="mt-1 break-words font-mono text-foreground-muted">
                                    {item.value}
                                  </p>
                                )}
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </div>
                  </div>
                </details>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
