"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export type StatusType =
  | "running"
  | "building"
  | "failed"
  | "stopped"
  | "healing"
  | "healthy"
  | "warning"
  | "critical";

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
  building: {
    dot: "status-dot-yellow",
    bg: "bg-warning/10 border-warning/20",
    text: "text-warning",
    label: "Building",
  },
  warning: {
    dot: "status-dot-yellow",
    bg: "bg-warning/10 border-warning/20",
    text: "text-warning",
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
  healing: {
    dot: "status-dot-blue",
    bg: "bg-info/10 border-info/20",
    text: "text-info",
    label: "Healing",
  },
};

export interface StatusBadgeProps {
  status: StatusType;
  label?: string;
  className?: string;
}

export function StatusBadge({
  status,
  label,
  className,
}: StatusBadgeProps) {
  const config = statusConfig[status];

  return (
    <motion.div
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
        config.bg,
        config.text,
        className
      )}
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
    >
      <span
        className={cn(
          "status-dot",
          config.dot,
          status === "stopped" && "bg-foreground-muted opacity-50"
        )}
      />
      <span>{label ?? config.label}</span>
    </motion.div>
  );
}
