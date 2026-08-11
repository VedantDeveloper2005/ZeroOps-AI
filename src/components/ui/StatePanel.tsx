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
  headingLevel?: 1 | 2 | 3;
};

const variants: Record<
  StatePanelVariant,
  { icon: LucideIcon; iconClassName: string; panelClassName: string; iconSurface: string }
> = {
  empty: {
    icon: CircleOff,
    iconClassName: "text-foreground-subtle",
    panelClassName: "border-border bg-card",
    iconSurface: "border-border bg-surface-subtle",
  },
  error: {
    icon: AlertCircle,
    iconClassName: "text-danger",
    panelClassName: "border-danger/25 bg-card",
    iconSurface: "border-danger/20 bg-danger-subtle",
  },
  info: {
    icon: Info,
    iconClassName: "text-info",
    panelClassName: "border-info/25 bg-card",
    iconSurface: "border-info/20 bg-info-subtle",
  },
  success: {
    icon: CheckCircle2,
    iconClassName: "text-success",
    panelClassName: "border-success/25 bg-card",
    iconSurface: "border-success/20 bg-success-subtle",
  },
  permission: {
    icon: LockKeyhole,
    iconClassName: "text-warning-hover",
    panelClassName: "border-warning/25 bg-card",
    iconSurface: "border-warning/20 bg-warning-subtle",
  },
  disconnected: {
    icon: PlugZap,
    iconClassName: "text-warning-hover",
    panelClassName: "border-warning/25 bg-card",
    iconSurface: "border-warning/20 bg-warning-subtle",
  },
};

export function StatePanel({
  title,
  description,
  variant = "empty",
  action,
  compact = false,
  className,
  headingLevel = 2,
}: StatePanelProps) {
  const config = variants[variant];
  const Icon = config.icon;
  const Heading = `h${headingLevel}` as "h1" | "h2" | "h3";
  const actionClassName = "ops-secondary mt-5";

  return (
    <div
      role={variant === "error" ? "alert" : variant === "success" ? "status" : undefined}
      className={cn(
        "rounded-2xl border text-center shadow-sm",
        compact ? "px-5 py-6" : "px-6 py-10 sm:px-10 sm:py-12",
        config.panelClassName,
        className,
      )}
    >
      <span className={cn("mx-auto grid place-items-center rounded-xl border", compact ? "h-10 w-10" : "h-12 w-12", config.iconSurface)}>
        <Icon size={compact ? 20 : 23} className={config.iconClassName} aria-hidden="true" />
      </span>
      <Heading className={cn("mt-4 font-semibold tracking-[-0.02em] text-foreground", headingLevel === 1 ? "text-xl sm:text-2xl" : "text-base")}>{title}</Heading>
      <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-foreground-muted">{description}</p>
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
