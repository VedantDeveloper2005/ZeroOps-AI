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
  warning: "bg-warning-subtle text-warning-hover",
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
    <article className="ops-surface min-h-[148px] p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-foreground-muted">{label}</p>
          <p className="mt-3 text-2xl font-semibold tracking-[-0.04em] text-foreground tabular-nums sm:text-[1.75rem]">{value}</p>
        </div>
        <span className={cn("grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-current/10", toneClasses[tone])}>
          <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
        </span>
      </div>
      {supportingText && <p className="mt-3 text-xs leading-5 text-foreground-subtle">{supportingText}</p>}
    </article>
  );
}
