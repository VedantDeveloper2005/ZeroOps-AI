import Link from "next/link";
import {
  AlertCircle,
  CheckCircle2,
  CircleOff,
  Info,
  LockKeyhole,
  PlugZap,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

type StatePanelVariant =
  | "empty"
  | "error"
  | "info"
  | "success"
  | "permission"
  | "disconnected";

type StatePanelProps = {
  title: string;
  description: string;
  variant?: StatePanelVariant;
  action?: {
    label: string;
    href?: string;
    onClick?: () => void;
  };
  compact?: boolean;
  className?: string;
};

const variants: Record<
  StatePanelVariant,
  { icon: LucideIcon; iconClassName: string; panelClassName: string }
> = {
  empty: {
    icon: CircleOff,
    iconClassName: "text-foreground-subtle",
    panelClassName: "border-border bg-card",
  },
  error: {
    icon: AlertCircle,
    iconClassName: "text-danger",
    panelClassName: "border-danger/25 bg-danger-subtle",
  },
  info: {
    icon: Info,
    iconClassName: "text-info",
    panelClassName: "border-info/25 bg-info-subtle",
  },
  success: {
    icon: CheckCircle2,
    iconClassName: "text-success",
    panelClassName: "border-success/25 bg-success-subtle",
  },
  permission: {
    icon: LockKeyhole,
    iconClassName: "text-warning",
    panelClassName: "border-warning/25 bg-warning-subtle",
  },
  disconnected: {
    icon: PlugZap,
    iconClassName: "text-warning",
    panelClassName: "border-warning/25 bg-warning-subtle",
  },
};

export function StatePanel({
  title,
  description,
  variant = "empty",
  action,
  compact = false,
  className,
}: StatePanelProps) {
  const config = variants[variant];
  const Icon = config.icon;
  const actionClassName =
    "mt-4 inline-flex min-h-10 items-center justify-center rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground shadow-sm transition-colors hover:bg-surface-raised";

  return (
    <div
      role={variant === "error" ? "alert" : variant === "success" ? "status" : undefined}
      className={cn(
        "rounded-xl border text-center",
        compact ? "px-5 py-6" : "px-6 py-10",
        config.panelClassName,
        className,
      )}
    >
      <Icon size={compact ? 22 : 28} className={cn("mx-auto", config.iconClassName)} />
      <h2 className="mt-3 text-sm font-semibold text-foreground">{title}</h2>
      <p className="mx-auto mt-1.5 max-w-lg text-xs leading-5 text-foreground-muted">{description}</p>
      {action?.href ? (
        <Link href={action.href} className={actionClassName}>
          {action.label}
        </Link>
      ) : action?.onClick ? (
        <button type="button" onClick={action.onClick} className={actionClassName}>
          {action.label}
        </button>
      ) : null}
    </div>
  );
}
