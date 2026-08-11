"use client";

import { useEffect, useRef } from "react";
import { AlertTriangle, Loader2, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel?: string;
  tone?: "danger" | "warning";
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  tone = "warning",
  busy = false,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const Icon = tone === "danger" ? AlertTriangle : ShieldCheck;

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="confirmation-dialog-title"
      aria-describedby="confirmation-dialog-description"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
      onClose={() => {
        if (open && !busy) onClose();
      }}
      className="m-auto w-[calc(100%_-_2rem)] max-w-lg rounded-2xl border border-border bg-card p-0 text-foreground shadow-2xl backdrop:bg-slate-950/60"
    >
      <div className="flex items-start gap-3 border-b border-border px-5 py-5">
        <span className={cn("grid h-10 w-10 shrink-0 place-items-center rounded-xl border", tone === "danger" ? "border-danger/20 bg-danger-subtle text-danger" : "border-warning/20 bg-warning-subtle text-warning-hover")}>
          <Icon size={19} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h2 id="confirmation-dialog-title" className="text-base font-semibold tracking-[-0.02em] text-foreground">{title}</h2>
          <p id="confirmation-dialog-description" className="mt-1.5 text-sm leading-6 text-foreground-muted">{description}</p>
        </div>
      </div>
      <div className="flex flex-col-reverse gap-2 px-5 py-4 sm:flex-row sm:justify-end">
        <button type="button" onClick={onClose} disabled={busy} className="ops-secondary disabled:opacity-50">{cancelLabel}</button>
        <button type="button" onClick={onConfirm} disabled={busy} className={cn(tone === "danger" ? "ops-danger" : "ops-primary", "disabled:opacity-50")}>
          {busy && <Loader2 size={15} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />}
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
