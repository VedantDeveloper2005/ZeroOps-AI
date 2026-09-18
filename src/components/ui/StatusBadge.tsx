import { cn } from "@/lib/utils";

export type StatusType =
  | "running"
  | "building"
  | "failed"
  | "stopped"
  | "healing"
  | "healthy"
  | "warning"
  | "critical"
  | "active"
  | "deploying"
  | "queued"
  | "rolled_back"
  | "archived";

const statusConfig: Record<
  StatusType,
  { dot: string; bg: string; text: string; label: string }
> = {
  running: {
    dot: "bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.7)]",
    bg: "bg-emerald-500/10 border-emerald-500/25 shadow-[0_0_12px_rgba(16,185,129,0.1)]",
    text: "text-emerald-400",
    label: "Running",
  },
  healthy: {
    dot: "bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.7)]",
    bg: "bg-emerald-500/10 border-emerald-500/25 shadow-[0_0_12px_rgba(16,185,129,0.1)]",
    text: "text-emerald-400",
    label: "Healthy",
  },
  active: {
    dot: "bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.7)]",
    bg: "bg-emerald-500/10 border-emerald-500/25 shadow-[0_0_12px_rgba(16,185,129,0.1)]",
    text: "text-emerald-400",
    label: "Active",
  },
  building: {
    dot: "bg-amber-400 shadow-[0_0_8px_rgba(245,158,11,0.7)] animate-pulse motion-reduce:animate-none",
    bg: "bg-amber-500/10 border-amber-500/25 shadow-[0_0_12px_rgba(245,158,11,0.1)]",
    text: "text-amber-400",
    label: "Building",
  },
  deploying: {
    dot: "bg-blue-400 shadow-[0_0_8px_rgba(59,130,246,0.8)] animate-pulse motion-reduce:animate-none",
    bg: "bg-blue-500/10 border-blue-500/25 shadow-[0_0_12px_rgba(59,130,246,0.15)]",
    text: "text-blue-400",
    label: "Deploying",
  },
  queued: {
    dot: "bg-amber-400 shadow-[0_0_6px_rgba(245,158,11,0.6)]",
    bg: "bg-amber-500/10 border-amber-500/25",
    text: "text-amber-400",
    label: "Queued",
  },
  rolled_back: {
    dot: "bg-amber-400 shadow-[0_0_6px_rgba(245,158,11,0.6)]",
    bg: "bg-amber-500/10 border-amber-500/25",
    text: "text-amber-400",
    label: "Rolled Back",
  },
  warning: {
    dot: "bg-amber-400 shadow-[0_0_8px_rgba(245,158,11,0.7)]",
    bg: "bg-amber-500/10 border-amber-500/25 shadow-[0_0_12px_rgba(245,158,11,0.1)]",
    text: "text-amber-400",
    label: "Warning",
  },
  failed: {
    dot: "bg-red-400 shadow-[0_0_8px_rgba(239,68,68,0.8)]",
    bg: "bg-red-500/10 border-red-500/25 shadow-[0_0_12px_rgba(239,68,68,0.15)]",
    text: "text-red-400",
    label: "Failed",
  },
  critical: {
    dot: "bg-red-400 shadow-[0_0_8px_rgba(239,68,68,0.8)] animate-pulse motion-reduce:animate-none",
    bg: "bg-red-500/10 border-red-500/25 shadow-[0_0_12px_rgba(239,68,68,0.15)]",
    text: "text-red-400",
    label: "Critical",
  },
  stopped: {
    dot: "bg-slate-500",
    bg: "bg-slate-800/40 border-slate-700/40",
    text: "text-slate-400",
    label: "Stopped",
  },
  archived: {
    dot: "bg-slate-500",
    bg: "bg-slate-800/40 border-slate-700/40",
    text: "text-slate-400",
    label: "Archived",
  },
  healing: {
    dot: "bg-blue-400 shadow-[0_0_8px_rgba(59,130,246,0.8)] animate-pulse motion-reduce:animate-none",
    bg: "bg-blue-500/10 border-blue-500/25 shadow-[0_0_12px_rgba(59,130,246,0.15)]",
    text: "text-blue-400",
    label: "Healing",
  },
};

export interface StatusBadgeProps {
  status: StatusType | string;
  label?: string;
  className?: string;
}

export function StatusBadge({
  status,
  label,
  className,
}: StatusBadgeProps) {
  const config = statusConfig[status as StatusType] || {
    dot: "bg-foreground-muted opacity-60",
    bg: "bg-foreground-muted/10 border-foreground-muted/20",
    text: "text-foreground-muted",
    label: status
      ? status.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase())
      : "Unknown",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
        config.bg,
        config.text,
        className
      )}
    >
      <span
        className={cn(
          "status-dot",
          config.dot,
          status === "stopped" && "bg-foreground-muted opacity-50"
        )}
      />
      <span>{label ?? config.label}</span>
    </span>
  );
}
