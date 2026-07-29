import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

type MetricCardProps = {
  label: string;
  value: string;
  supportingText?: string;
  icon: LucideIcon;
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
};

const toneClasses = {
  neutral: "bg-surface-subtle text-foreground-muted",
  success: "bg-success-subtle text-success",
  warning: "bg-warning-subtle text-warning",
  danger: "bg-danger-subtle text-danger",
  info: "bg-info-subtle text-info",
} as const;

export function MetricCard({
  label,
  value,
  supportingText,
  icon: Icon,
  tone = "neutral",
}: MetricCardProps) {
  return (
    <article className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium text-foreground-muted">{label}</p>
          <p className="mt-2 text-2xl font-semibold tracking-[-0.035em] text-foreground tabular-nums">{value}</p>
        </div>
        <span className={cn("grid h-9 w-9 shrink-0 place-items-center rounded-lg", toneClasses[tone])}>
          <Icon size={17} />
        </span>
      </div>
      {supportingText && <p className="mt-2 text-[11px] leading-4 text-foreground-subtle">{supportingText}</p>}
    </article>
  );
}
