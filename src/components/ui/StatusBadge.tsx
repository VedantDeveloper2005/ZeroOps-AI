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
    dot: "status-dot-green",
    bg: "bg-success/10 border-success/20",
    text: "text-success",
    label: "Running",
  },
  healthy: {
    dot: "status-dot-green",
    bg: "bg-success/10 border-success/20",
    text: "text-success",
    label: "Healthy",
  },
  active: {
    dot: "status-dot-green",
    bg: "bg-success/10 border-success/20",
    text: "text-success",
    label: "Active",
  },
  building: {
    dot: "status-dot-yellow",
    bg: "bg-warning/10 border-warning/20",
    text: "text-warning",
    label: "Building",
  },
  deploying: {
    dot: "status-dot-blue",
    bg: "bg-info/10 border-info/20",
    text: "text-info",
    label: "Deploying",
  },
  queued: {
    dot: "status-dot-yellow",
    bg: "bg-warning/10 border-warning/20",
    text: "text-warning",
    label: "Queued",
  },
  rolled_back: {
    dot: "status-dot-yellow",
    bg: "bg-warning/10 border-warning/20",
    text: "text-warning",
    label: "Rolled Back",
  },
  warning: {
    dot: "status-dot-yellow",
    bg: "bg-warning/10 border-warning/20",
    text: "text-warning-hover",
    label: "Warning",
  },
  failed: {
    dot: "status-dot-red",
    bg: "bg-danger/10 border-danger/20",
    text: "text-danger",
    label: "Failed",
  },
  critical: {
    dot: "status-dot-red",
    bg: "bg-danger/10 border-danger/20",
    text: "text-danger",
    label: "Critical",
  },
  stopped: {
    dot: "",
    bg: "bg-foreground-muted/10 border-foreground-muted/20",
    text: "text-foreground-muted",
    label: "Stopped",
  },
  archived: {
    dot: "",
    bg: "bg-foreground-muted/10 border-foreground-muted/20",
    text: "text-foreground-muted",
    label: "Archived",
  },
  healing: {
    dot: "status-dot-blue",
    bg: "bg-info/10 border-info/20",
    text: "text-info",
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
