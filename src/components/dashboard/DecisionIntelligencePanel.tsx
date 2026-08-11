"use client";

import {
  CheckCircle2,
  CircleAlert,
  ClipboardCheck,
  Loader2,
  Play,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import type { DigitalTwinSimulation } from "@/lib/api";

type Props = {
  preflight: DigitalTwinSimulation | null;
  loading?: boolean;
  onRunPreflight: () => Promise<void>;
};

const stateStyle = {
  ready: "border-success/25 bg-success/10 text-success",
  requires_review: "border-warning/25 bg-warning/10 text-warning",
  blocked: "border-danger/25 bg-danger/10 text-danger",
} as const;

const stateLabel = {
  ready: "Checks passed",
  requires_review: "Review needed",
  blocked: "Blocked",
} as const;

const checkStyle = {
  passed: "text-success",
  warning: "text-warning",
  blocked: "text-danger",
} as const;

export function DecisionIntelligencePanel({
  preflight,
  loading = false,
  onRunPreflight,
}: Props) {
  const passedChecks = preflight?.checks.filter((check) => check.status === "passed") ?? [];
  const warningChecks = preflight?.checks.filter((check) => check.status === "warning") ?? [];
  const blockedChecks = preflight?.checks.filter((check) => check.status === "blocked") ?? [];
  const attentionChecks = [...blockedChecks, ...warningChecks];

  return (
    <section aria-labelledby="preflight-heading" className="space-y-5">
      <div className="flex flex-col gap-4 border-y border-border py-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-semibold text-primary">Deterministic policy check</p>
          <h2
            id="preflight-heading"
            className="mt-1 text-xl font-semibold tracking-tight text-foreground"
          >
            Pre-deployment checks
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-foreground-muted">
            Check the saved plan, repository analysis, approval state, and recorded Azure target
            readiness. This is a rules-based gate, not a cloud simulation or a prediction of
            deployment success.
          </p>
        </div>
        <button
          type="button"
          disabled={loading}
          onClick={() => void onRunPreflight()}
          className="ops-primary min-h-11 shrink-0 px-4 text-sm disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? (
            <Loader2 size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
          ) : (
            <Play size={16} aria-hidden="true" />
          )}
          {loading ? "Running checks" : "Run checks"}
        </button>
      </div>

      <article className="ops-card rounded-2xl p-5 sm:p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <ClipboardCheck size={18} className="text-primary" aria-hidden="true" />
              <h3 className="text-base font-semibold text-foreground">Latest recorded result</h3>
            </div>
            <p className="mt-1.5 max-w-2xl text-xs leading-5 text-foreground-muted">
              Results apply only to the plan revision shown below. Editing the plan makes this
              record stale until checks run again.
            </p>
          </div>
          {preflight && (
            <span
              className={`inline-flex w-fit shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${stateStyle[preflight.status]}`}
            >
              {stateLabel[preflight.status]}
            </span>
          )}
        </div>

        {preflight ? (
          <>
            <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <ResultItem label="Plan revision" value={`v${preflight.plan_revision ?? "—"}`} />
              <ResultItem label="Passed" value={String(passedChecks.length)} tone="success" />
              <ResultItem label="Warnings" value={String(warningChecks.length)} tone="warning" />
              <ResultItem label="Blocked" value={String(blockedChecks.length)} tone="danger" />
              <ResultItem label="Rule set" value={preflight.model || "Not recorded"} />
            </dl>

            <p className="mt-4 text-xs leading-5 text-foreground-muted">{preflight.summary}</p>

            {attentionChecks.length > 0 ? (
              <div className="mt-5 space-y-2.5">
                <p className="text-xs font-semibold text-foreground">Items to address</p>
                {attentionChecks.map((check) => (
                  <CheckRow key={check.id} check={check} />
                ))}
              </div>
            ) : (
              <div className="mt-5 flex gap-3 rounded-xl border border-success/25 bg-success/10 p-4">
                <CheckCircle2
                  size={18}
                  className="mt-0.5 shrink-0 text-success"
                  aria-hidden="true"
                />
                <div>
                  <p className="text-sm font-semibold text-foreground">
                    No blocking or warning checks were recorded
                  </p>
                  <p className="mt-1 text-xs leading-5 text-foreground-muted">
                    Deployment still has to provision the target and pass its runtime health
                    check.
                  </p>
                </div>
              </div>
            )}

            {passedChecks.length > 0 && (
              <details className="mt-4 rounded-xl border border-border px-3 py-2.5">
                <summary className="flex min-h-11 cursor-pointer items-center text-xs font-medium text-foreground">
                  Show {passedChecks.length} passed check
                  {passedChecks.length === 1 ? "" : "s"}
                </summary>
                <div className="mt-3 space-y-2">
                  {passedChecks.map((check) => (
                    <CheckRow key={check.id} check={check} compact />
                  ))}
                </div>
              </details>
            )}
          </>
        ) : (
          <div className="mt-5 flex min-h-24 items-center gap-3 rounded-xl border border-dashed border-border bg-background-secondary/35 p-4">
            <ClipboardCheck
              size={18}
              className="shrink-0 text-foreground-muted"
              aria-hidden="true"
            />
            <p className="text-xs leading-5 text-foreground-muted">
              No check result exists for this plan revision. Running checks does not create or
              modify Azure resources.
            </p>
          </div>
        )}
      </article>

      <aside
        aria-label="Preflight limitations"
        className="rounded-xl border border-border bg-card px-4 py-4"
      >
        <div className="flex items-start gap-3">
          <ShieldCheck size={18} className="mt-0.5 shrink-0 text-primary" aria-hidden="true" />
          <div>
            <p className="text-sm font-semibold text-foreground">What these checks do not prove</p>
            <p className="mt-1 text-xs leading-5 text-foreground-muted">
              They do not certify security, quote Azure costs, measure performance or reliability,
              inspect live application health, or guarantee a successful release. The deployment
              workflow reruns its prerequisites and records the actual outcome.
            </p>
          </div>
        </div>
      </aside>
    </section>
  );
}

function ResultItem({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "success" | "warning" | "danger";
}) {
  const valueColor =
    tone === "success"
      ? "text-success"
      : tone === "warning"
        ? "text-warning"
        : tone === "danger"
          ? "text-danger"
          : "text-foreground";

  return (
    <div className="rounded-xl border border-border bg-background-secondary/35 px-3 py-3">
      <dt className="text-xs font-medium text-foreground-muted">{label}</dt>
      <dd className={`mt-1 text-sm font-semibold break-words ${valueColor}`}>{value}</dd>
    </div>
  );
}

function CheckRow({
  check,
  compact = false,
}: {
  check: DigitalTwinSimulation["checks"][number];
  compact?: boolean;
}) {
  const Icon =
    check.status === "passed"
      ? CheckCircle2
      : check.status === "warning"
        ? CircleAlert
        : XCircle;

  return (
    <div
      className={`flex gap-2.5 rounded-xl border border-border px-3 py-2.5 ${
        compact ? "bg-background-secondary/35" : "bg-card"
      }`}
    >
      <Icon
        size={16}
        className={`mt-0.5 shrink-0 ${checkStyle[check.status]}`}
        aria-hidden="true"
      />
      <div className="min-w-0">
        <p className="text-xs font-semibold text-foreground">{check.label}</p>
        <p className="mt-0.5 text-xs leading-5 text-foreground-muted">{check.detail}</p>
      </div>
    </div>
  );
}
