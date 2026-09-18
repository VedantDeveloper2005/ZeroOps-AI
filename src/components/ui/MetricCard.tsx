import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

type MetricCardProps = {
  label: string;
  value: string;
  supportingText?: string;
  icon: LucideIcon;
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
  trend?: string;
};

const toneClasses = {
  neutral: "bg-slate-800/40 border-slate-700/40 text-slate-400",
  success: "bg-emerald-500/10 border-emerald-500/20 text-emerald-400",
  warning: "bg-amber-500/10 border-amber-500/20 text-amber-400",
  danger: "bg-red-500/10 border-red-500/20 text-red-400",
  info: "bg-blue-500/10 border-blue-500/20 text-blue-400",
} as const;

export function MetricCard({
  label,
  value,
  supportingText,
  icon: Icon,
  tone = "neutral",
  trend,
}: MetricCardProps) {
  return (
    <article className="group relative rounded-xl border border-border bg-card p-4.5 shadow-xs transition-all duration-200 hover:border-slate-700/80 hover:shadow-md">
      <div className="flex items-center justify-between gap-3.5">
        <div className="flex items-center gap-3.5 min-w-0">
          <div
            className={cn(
              "flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border transition-transform duration-200 group-hover:scale-105",
              toneClasses[tone],
            )}
          >
            <Icon size={20} strokeWidth={2} aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-2xl font-bold tracking-tight text-foreground tabular-nums">
              {value}
            </p>
            <p className="truncate text-xs font-medium text-foreground-subtle">
              {label}
            </p>
          </div>
        </div>

        {trend ? (
          <div className="text-right flex flex-col items-end shrink-0">
            <svg
              className={cn(
                "h-5 w-12",
                tone === "success"
                  ? "text-emerald-400 drop-shadow-[0_0_4px_rgba(16,185,129,0.4)]"
                  : tone === "danger"
                    ? "text-red-400 drop-shadow-[0_0_4px_rgba(239,68,68,0.4)]"
                    : "text-blue-400 drop-shadow-[0_0_4px_rgba(59,130,246,0.4)]",
              )}
              fill="none"
              viewBox="0 0 60 20"
            >
              <path
                d="M2 15 Q 15 13, 25 9 T 45 5 T 58 2"
                stroke="currentColor"
                strokeLinecap="round"
                strokeWidth="2"
              />
            </svg>
            <span
              className={cn(
                "mt-0.5 text-[11px] font-semibold tabular-nums",
                tone === "success"
                  ? "text-emerald-400"
                  : tone === "danger"
                    ? "text-red-400"
                    : "text-blue-400",
              )}
            >
              {trend}
            </span>
          </div>
        ) : supportingText ? (
          <p className="text-right text-[11px] font-medium text-foreground-subtle">
            {supportingText}
          </p>
        ) : null}
      </div>
    </article>
  );
}
