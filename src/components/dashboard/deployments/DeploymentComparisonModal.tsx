"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  CheckCircle2,
  CircleStop,
  Clock3,
  GitCompare,
  Loader2,
  RotateCcw,
  X,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import type { Deployment } from "@/lib/api";

type DeploymentItem = Pick<
  Deployment,
  | "id"
  | "status"
  | "commit_sha"
  | "started_at"
  | "completed_at"
  | "environment"
  | "live_url"
>;

interface DeploymentComparisonModalProps {
  isOpen: boolean;
  onClose: () => void;
  current: DeploymentItem | null;
  previous: DeploymentItem | null;
}

type StatusPresentation = {
  label: string;
  className: string;
  icon: LucideIcon;
  iconClassName?: string;
};

const statusPresentations: Record<Deployment["status"], StatusPresentation> = {
  queued: {
    label: "Queued",
    className: "border-warning/25 bg-warning-subtle text-warning",
    icon: Clock3,
  },
  building: {
    label: "Building",
    className: "border-warning/25 bg-warning-subtle text-warning",
    icon: Loader2,
    iconClassName: "animate-spin motion-reduce:animate-none",
  },
  deploying: {
    label: "Deploying",
    className: "border-info/25 bg-info-subtle text-info",
    icon: Loader2,
    iconClassName: "animate-spin motion-reduce:animate-none",
  },
  running: {
    label: "Running",
    className: "border-success/25 bg-success-subtle text-success",
    icon: CheckCircle2,
  },
  failed: {
    label: "Failed",
    className: "border-danger/25 bg-danger-subtle text-danger",
    icon: XCircle,
  },
  stopped: {
    label: "Stopped",
    className:
      "border-foreground-muted/25 bg-foreground-muted/10 text-foreground-muted",
    icon: CircleStop,
  },
  rolled_back: {
    label: "Rolled back",
    className: "border-warning/25 bg-warning-subtle text-warning",
    icon: RotateCcw,
  },
};

const easeOut = [0.22, 1, 0.36, 1] as const;
const focusableSelector = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function formatCommit(sha?: string | null): string {
  if (!sha) return "Not recorded";
  return sha.length > 8 ? sha.slice(0, 8) : sha;
}

function formatDeploymentDate(deployment: DeploymentItem): string {
  const value = deployment.completed_at || deployment.started_at;
  if (!value) return "Not recorded";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not recorded" : date.toLocaleString();
}

function DeploymentStatus({ status }: { status: Deployment["status"] }) {
  const presentation = statusPresentations[status];
  const Icon = presentation.icon;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${presentation.className}`}
    >
      <Icon
        aria-hidden="true"
        size={12}
        className={presentation.iconClassName}
      />
      {presentation.label}
    </span>
  );
}

function DeploymentCard({
  deployment,
  label,
  current = false,
}: {
  deployment: DeploymentItem;
  label: string;
  current?: boolean;
}) {
  return (
    <article
      className={
        current
          ? "space-y-4 rounded-xl border border-primary/25 bg-primary-subtle/30 p-4"
          : "space-y-4 rounded-xl border border-border bg-background p-4"
      }
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3
          className={`text-xs font-semibold uppercase tracking-wider ${
            current ? "text-primary" : "text-foreground-muted"
          }`}
        >
          {label}
        </h3>
        <DeploymentStatus status={deployment.status} />
      </div>

      <dl className="space-y-2 text-xs">
        <div className="flex items-start justify-between gap-4 border-b border-border/50 pb-2">
          <dt className="shrink-0 text-foreground-muted">Commit</dt>
          <dd className="break-all text-right font-mono font-semibold text-foreground">
            {formatCommit(deployment.commit_sha)}
          </dd>
        </div>
        <div className="flex items-start justify-between gap-4 border-b border-border/50 pb-2">
          <dt className="shrink-0 text-foreground-muted">Release time</dt>
          <dd className="text-right text-foreground">
            {formatDeploymentDate(deployment)}
          </dd>
        </div>
        <div className="flex items-start justify-between gap-4 border-b border-border/50 pb-2">
          <dt className="shrink-0 text-foreground-muted">Environment</dt>
          <dd className="text-right font-medium capitalize text-foreground">
            {deployment.environment}
          </dd>
        </div>
        <div className="flex items-start justify-between gap-4">
          <dt className="shrink-0 text-foreground-muted">Live URL</dt>
          <dd className="max-w-[12rem] break-all text-right font-mono text-[11px] text-foreground-subtle">
            {deployment.live_url || "Not recorded"}
          </dd>
        </div>
      </dl>
    </article>
  );
}

export function DeploymentComparisonModal({
  isOpen,
  onClose,
  current,
  previous,
}: DeploymentComparisonModalProps) {
  const reduceMotion = useReducedMotion();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  const open = isOpen && current !== null;

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;

    returnFocusRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const focusFrame = window.requestAnimationFrame(() => {
      closeButtonRef.current?.focus();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onCloseRef.current();
        return;
      }

      if (event.key !== "Tab") return;
      const dialog = dialogRef.current;
      if (!dialog) return;

      const focusableElements = Array.from(
        dialog.querySelectorAll<HTMLElement>(focusableSelector),
      );
      if (focusableElements.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }

      const first = focusableElements[0];
      const last = focusableElements[focusableElements.length - 1];
      const activeElement = document.activeElement;

      if (
        event.shiftKey &&
        (activeElement === first || !dialog.contains(activeElement))
      ) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        (activeElement === last || !dialog.contains(activeElement))
      ) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      returnFocusRef.current?.focus();
      returnFocusRef.current = null;
    };
  }, [open]);

  return (
    <AnimatePresence>
      {isOpen && current ? (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/50 p-4 backdrop-blur-sm"
          initial={reduceMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reduceMotion ? 0 : 0.15 }}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) onCloseRef.current();
          }}
        >
          <motion.div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="deployment-comparison-title"
            aria-describedby="deployment-comparison-description"
            tabIndex={-1}
            initial={reduceMotion ? false : { opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.96 }}
            transition={{ duration: reduceMotion ? 0 : 0.2, ease: easeOut }}
            className="relative max-h-[calc(100dvh-2rem)] w-full max-w-3xl overflow-y-auto rounded-2xl border border-border bg-card shadow-2xl outline-none"
          >
            <header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4 sm:px-6">
              <div className="flex min-w-0 items-start gap-3">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-primary/20 bg-primary-subtle text-primary">
                  <GitCompare aria-hidden="true" size={17} />
                </span>
                <div className="min-w-0">
                  <h2
                    id="deployment-comparison-title"
                    className="text-base font-semibold text-foreground"
                  >
                    Compare releases
                  </h2>
                  <p
                    id="deployment-comparison-description"
                    className="mt-1 text-xs leading-5 text-foreground-muted"
                  >
                    Current deployment and the immediately preceding recorded
                    deployment for this project.
                  </p>
                </div>
              </div>
              <button
                ref={closeButtonRef}
                type="button"
                onClick={onClose}
                aria-label="Close release comparison"
                className="grid min-h-11 min-w-11 shrink-0 place-items-center rounded-lg text-foreground-muted transition-colors hover:bg-surface-subtle hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                <X aria-hidden="true" size={18} />
              </button>
            </header>

            <div className="p-5 sm:p-6">
              {!previous ? (
                <div className="rounded-xl border border-dashed border-border px-5 py-10 text-center">
                  <p className="text-sm font-semibold text-foreground">
                    No earlier release is available
                  </p>
                  <p className="mx-auto mt-2 max-w-md text-xs leading-5 text-foreground-muted">
                    No older deployment with a recorded start time was found for
                    this project in the loaded history.
                  </p>
                </div>
              ) : (
                <div className="grid gap-5 sm:grid-cols-2">
                  <DeploymentCard
                    deployment={current}
                    label="Current release"
                    current
                  />
                  <DeploymentCard
                    deployment={previous}
                    label="Previous release"
                  />
                </div>
              )}
            </div>

            <footer className="flex justify-end border-t border-border px-5 py-3 sm:px-6">
              <button
                type="button"
                onClick={onClose}
                className="inline-flex min-h-11 items-center rounded-lg border border-border bg-card px-4 text-xs font-semibold text-foreground transition-colors hover:border-border-hover hover:bg-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                Close
              </button>
            </footer>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
