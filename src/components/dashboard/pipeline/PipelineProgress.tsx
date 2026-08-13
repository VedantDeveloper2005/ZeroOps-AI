"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Clock3, Loader2, XCircle } from "lucide-react";
import type { PipelineRunStatus, PipelineStageAttempt, PipelineStageStatus } from "@/lib/api";

function formatElapsed(
  startedAt: string | null | undefined,
  completedAt?: string | null,
): string {
  if (!startedAt) return "—";
  const start = new Date(startedAt);
  if (Number.isNaN(start.getTime())) return "—";
  const completed = completedAt ? new Date(completedAt) : null;
  const endTime = completed && !Number.isNaN(completed.getTime()) ? completed.getTime() : Date.now();
  const elapsed = endTime - start.getTime();
  const seconds = Math.max(0, Math.floor(elapsed / 1000));
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}h ${mins.toString().padStart(2, "0")}m`;
  }
  return minutes > 0
    ? `${minutes}m ${remaining.toString().padStart(2, "0")}s`
    : `${remaining}s`;
}

const terminalStatuses = new Set<PipelineStageStatus>([
  "succeeded",
  "failed",
  "skipped",
  "blocked",
  "unavailable",
  "cancelled",
]);

function stageSummaryLine(stages: PipelineStageAttempt[]): string {
  const items: string[] = [];
  for (const stage of stages) {
    const label = stage.name || stage.stage_key;
    if (stage.status === "succeeded") {
      items.push(`${label} ✓`);
    } else if (stage.status === "running") {
      items.push(`${label}…`);
    } else if (stage.status === "failed") {
      items.push(`${label} ✗`);
    }
  }
  return items.slice(-4).join(" · ");
}

interface PipelineProgressProps {
  status: PipelineRunStatus;
  stages: PipelineStageAttempt[];
  startedAt: string | null | undefined;
  completedAt: string | null | undefined;
}

export function PipelineProgress({
  status,
  stages,
  startedAt,
  completedAt,
}: PipelineProgressProps) {
  const [elapsed, setElapsed] = useState(() => formatElapsed(startedAt, completedAt));
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const completed = stages.filter((stage) => terminalStatuses.has(stage.status)).length;
  const total = stages.length;
  const progress = total > 0 ? Math.round((completed / total) * 100) : 0;
  const isTerminal = status !== "queued" && status !== "running";

  useEffect(() => {
    if (isTerminal || !startedAt) {
      setElapsed(formatElapsed(startedAt, completedAt));
      return;
    }
    setElapsed(formatElapsed(startedAt));
    intervalRef.current = setInterval(() => {
      setElapsed(formatElapsed(startedAt));
    }, 1000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [startedAt, completedAt, isTerminal]);

  const succeeded = stages.filter((stage) => stage.status === "succeeded").length;
  const failed = stages.filter((stage) => stage.status === "failed").length;
  const running = stages.filter((stage) => stage.status === "running").length;

  const barColor =
    status === "failed"
      ? "bg-danger"
      : status === "succeeded"
        ? "bg-success"
        : "bg-primary";

  return (
    <div className="rounded-xl border border-border bg-card">
      {/* Top row */}
      <div className="flex items-center justify-between gap-4 px-4 py-3">
        <div className="flex items-center gap-2">
          {status === "running" ? (
            <Loader2
              aria-hidden="true"
              size={15}
              className="animate-spin text-info motion-reduce:animate-none"
            />
          ) : status === "succeeded" ? (
            <CheckCircle2 aria-hidden="true" size={15} className="text-success" />
          ) : status === "failed" ? (
            <XCircle aria-hidden="true" size={15} className="text-danger" />
          ) : (
            <Clock3 aria-hidden="true" size={15} className="text-foreground-subtle" />
          )}
          <span className="text-xs font-semibold text-foreground">
            {status === "running"
              ? "Pipeline running"
              : status === "succeeded"
                ? "Pipeline succeeded"
                : status === "failed"
                  ? "Pipeline failed"
                  : status === "queued"
                    ? "Pipeline queued"
                    : `Pipeline ${status}`}
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="font-mono text-foreground-subtle">{elapsed}</span>
          <span className="font-semibold text-primary">{progress}%</span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="px-4 pb-2">
        <div className="h-1.5 overflow-hidden rounded-full bg-border/60">
          <div
            className={`h-full rounded-full transition-all duration-500 ease-out ${barColor}`}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Summary stats */}
      <div className="flex items-center gap-4 border-t border-border px-4 py-2.5 text-xs text-foreground-muted">
        {succeeded > 0 ? (
          <span className="inline-flex items-center gap-1 text-success">
            <CheckCircle2 aria-hidden="true" size={12} />
            {succeeded} passed
          </span>
        ) : null}
        {failed > 0 ? (
          <span className="inline-flex items-center gap-1 text-danger">
            <XCircle aria-hidden="true" size={12} />
            {failed} failed
          </span>
        ) : null}
        {running > 0 ? (
          <span className="inline-flex items-center gap-1 text-info">
            <Loader2 aria-hidden="true" size={12} className="animate-spin motion-reduce:animate-none" />
            {running} running
          </span>
        ) : null}
        <span className="ml-auto truncate text-foreground-subtle">
          {stageSummaryLine(stages) || `${total} stages`}
        </span>
      </div>
    </div>
  );
}
