"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FileCheck2,
  Loader2,
  LockKeyhole,
  RefreshCw,
  Rocket,
  ShieldCheck,
} from "lucide-react";
import {
  api,
  getErrorMessage,
  type TerraformApplyApprovalRequest,
  type TerraformPlanActionCounts,
  type TerraformReview,
  type TerraformReviewStatus,
} from "@/lib/api";

type TerraformReviewAction = "cost" | "apply" | null;

type Props = {
  projectId: string;
  revision: number;
  disabled?: boolean;
  deploymentBusy?: boolean;
  onStartDeployment: () => Promise<void>;
};

const POLLING_STATUSES = new Set<TerraformReviewStatus>(["planning", "applying"]);
const ACTION_KEYS: (keyof TerraformPlanActionCounts)[] = [
  "create",
  "update",
  "delete",
  "replace",
  "read",
  "no_op",
];

const ACTION_LABELS: Record<keyof TerraformPlanActionCounts, string> = {
  create: "Create",
  update: "Update",
  delete: "Delete",
  replace: "Replace",
  read: "Read",
  no_op: "No-op",
};

function statusCopy(status: TerraformReviewStatus) {
  switch (status) {
    case "not_approved":
      return {
        title: "Architecture approval required",
        detail: "Approve this architecture revision before Terraform planning can begin.",
      };
    case "not_queued":
      return {
        title: "Terraform generation is not queued",
        detail: "This approved revision has no matching isolated Terraform run. Create a new revision and approve it again.",
      };
    case "planning":
      return {
        title: "Generating the exact Terraform plan",
        detail: "The isolated runner is validating a saved plan for this architecture revision.",
      };
    case "awaiting_verified_cost":
      return {
        title: "Plan ready; cost evidence required",
        detail: "Review the resource changes, then verify the exact incremental fixed cost before approval.",
      };
    case "ready_for_approval":
      return {
        title: "Exact plan ready for approval",
        detail: "Review every address, action, guardrail, and cost binding before authorizing one apply.",
      };
    case "applying":
      return {
        title: "Applying the approved saved plan",
        detail: "The one-time approval was consumed. Deployment remains locked until Azure apply completes.",
      };
    case "applied":
      return {
        title: "Terraform apply completed",
        detail: "The current architecture revision and verified Azure target now have exact apply proof.",
      };
    case "failed":
      return {
        title: "Terraform workflow failed",
        detail: "No application deployment can start from this run. Review the recorded failure before creating a new revision.",
      };
  }
}

function formatMicrounits(amount: number, currency: string) {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 6,
    }).format(amount / 1_000_000);
  } catch {
    return `${currency} ${(amount / 1_000_000).toFixed(6)}`;
  }
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) return "Not recorded";
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return "Not recorded";
  return timestamp.toLocaleString();
}

function approvalRequestFor(review: TerraformReview): TerraformApplyApprovalRequest | null {
  const verifiedCost = review.verified_cost;
  const stringBindings = [
    review.plan_job_digest,
    review.plan_sha256,
    review.bundle_sha256,
    review.input_variables_sha256,
    review.scope_digest,
    review.policy_digest,
    verifiedCost?.artifact_sha256,
    verifiedCost?.currency,
  ];
  if (
    !review.operation_run_id ||
    !review.guardrails ||
    !review.plan_summary ||
    !verifiedCost ||
    stringBindings.some((value) => typeof value !== "string" || value.length === 0)
  ) {
    return null;
  }

  return {
    confirm_apply: true,
    plan_job_digest: review.plan_job_digest as string,
    plan_sha256: review.plan_sha256 as string,
    bundle_sha256: review.bundle_sha256 as string,
    input_variables_sha256: review.input_variables_sha256 as string,
    scope_digest: review.scope_digest as string,
    policy_digest: review.policy_digest as string,
    cost_estimate_sha256: verifiedCost.artifact_sha256,
    currency: verifiedCost.currency,
    monthly_cost_microunits: verifiedCost.monthly_cost_microunits,
  };
}

export function TerraformApplyReview({
  projectId,
  revision,
  disabled = false,
  deploymentBusy = false,
  onStartDeployment,
}: Props) {
  const [review, setReview] = useState<TerraformReview | null>(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<TerraformReviewAction>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const requestSequence = useRef(0);
  const operationBinding = useRef<string | null>(null);

  const refreshReview = useCallback(
    async (showLoading: boolean) => {
      const sequence = ++requestSequence.current;
      if (showLoading) setLoading(true);
      try {
        const nextReview = await api.getTerraformReview(projectId);
        if (sequence !== requestSequence.current) return;
        if (
          nextReview.project_id !== projectId ||
          (nextReview.revision !== undefined && nextReview.revision !== revision)
        ) {
          setReview(null);
          setConfirmed(false);
          setError("The Terraform review no longer matches this architecture revision. Reload the current plan before continuing.");
          return;
        }
        if (
          operationBinding.current !== (nextReview.operation_run_id ?? null) ||
          nextReview.status !== "ready_for_approval"
        ) {
          setConfirmed(false);
        }
        operationBinding.current = nextReview.operation_run_id ?? null;
        setReview(nextReview);
        setError(null);
      } catch (requestError) {
        if (sequence !== requestSequence.current) return;
        setError(getErrorMessage(requestError, "The exact Terraform review could not be loaded."));
      } finally {
        if (sequence === requestSequence.current && showLoading) setLoading(false);
      }
    },
    [projectId, revision],
  );

  useEffect(() => {
    operationBinding.current = null;
    setReview(null);
    setConfirmed(false);
    setError(null);
    setFeedback(null);
    void refreshReview(true);
    return () => {
      requestSequence.current += 1;
    };
  }, [refreshReview]);

  const isPolling = Boolean(review && POLLING_STATUSES.has(review.status));
  useEffect(() => {
    if (!isPolling) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      await refreshReview(false);
      if (!cancelled) timer = setTimeout(poll, 4_000);
    };
    timer = setTimeout(poll, 4_000);

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [isPolling, refreshReview]);

  const approvalRequest = useMemo(
    () => (review ? approvalRequestFor(review) : null),
    [review],
  );
  const reviewIsCurrent = review?.revision === revision;
  const applyProofIsCurrent = Boolean(
    review?.status === "applied" &&
      reviewIsCurrent &&
      review.operation_run_id &&
      review.apply_proof?.operation_run_id === review.operation_run_id,
  );
  const interactionDisabled = disabled || action !== null;

  const issueCostEvidence = async () => {
    if (!review?.operation_run_id || interactionDisabled) return;
    setAction("cost");
    setError(null);
    setFeedback(null);
    try {
      await api.issueTerraformCostEvidence(review.operation_run_id);
      setConfirmed(false);
      setFeedback("Verified incremental fixed-cost evidence is now bound to this saved plan.");
      await refreshReview(false);
    } catch (requestError) {
      setError(getErrorMessage(requestError, "Cost evidence could not be verified for this plan."));
    } finally {
      setAction(null);
    }
  };

  const approveApply = async () => {
    if (
      !review?.operation_run_id ||
      review.status !== "ready_for_approval" ||
      !reviewIsCurrent ||
      !approvalRequest ||
      !confirmed ||
      interactionDisabled
    ) {
      setError("Review the complete current plan and select the confirmation before approving apply.");
      return;
    }
    setAction("apply");
    setError(null);
    setFeedback(null);
    try {
      await api.approveTerraformApply(review.operation_run_id, approvalRequest);
      setConfirmed(false);
      setFeedback("The one-time approval was consumed. Waiting for the isolated Azure apply to complete.");
      setReview((current) => (current ? { ...current, status: "applying" } : current));
      await refreshReview(false);
    } catch (requestError) {
      setError(getErrorMessage(requestError, "The exact Terraform plan could not be approved."));
    } finally {
      setAction(null);
    }
  };

  const state = review
    ? statusCopy(review.status)
    : {
        title: "Terraform review unavailable",
        detail: "Refresh the current control record before continuing.",
      };
  const StateIcon = review?.status === "applied"
    ? CheckCircle2
    : !review || review.status === "failed" || review.status === "not_queued"
      ? AlertTriangle
      : isPolling
        ? Loader2
        : FileCheck2;
  const stateTone = review?.status === "applied"
    ? "border-success/25 bg-success/10"
    : !review || review.status === "failed" || review.status === "not_queued"
      ? "border-danger/25 bg-danger/10"
      : "border-primary/20 bg-primary-subtle";
  const stateIconTone = review?.status === "applied"
    ? "text-success"
    : !review || review.status === "failed" || review.status === "not_queued"
      ? "text-danger"
      : "text-primary";
  const verifiedCost = review?.verified_cost;
  const guardrails = review?.guardrails;
  const summary = review?.plan_summary;
  const exactBindings = review
    ? [
        ["Plan job digest", review.plan_job_digest],
        ["Saved plan SHA-256", review.plan_sha256],
        ["Terraform bundle SHA-256", review.bundle_sha256],
        ["Input variables SHA-256", review.input_variables_sha256],
        ["Scope digest", review.scope_digest],
        ["Policy digest", review.policy_digest],
      ]
    : [];

  return (
    <section
      aria-labelledby="terraform-review-heading"
      aria-busy={loading || isPolling || action !== null}
      className="ops-card rounded-2xl border border-border bg-card p-5 sm:p-6"
    >
      <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <ShieldCheck size={18} className="text-primary" aria-hidden="true" />
            <h2 id="terraform-review-heading" className="text-base font-semibold text-foreground">
              Exact Terraform review and apply
            </h2>
          </div>
          <p className="mt-2 max-w-3xl text-xs leading-5 text-foreground-muted">
            Architecture approval generates a saved plan only. Azure infrastructure changes require
            a separate, one-time approval of the exact plan, guardrails, target, and verified cost.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refreshReview(true)}
          disabled={loading || interactionDisabled}
          className="ops-secondary min-h-11 shrink-0 px-3 text-xs disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RefreshCw
            size={14}
            className={loading ? "animate-spin motion-reduce:animate-none" : ""}
            aria-hidden="true"
          />
          Refresh status
        </button>
      </div>

      {loading && !review ? (
        <div role="status" className="flex min-h-32 items-center justify-center gap-2 text-sm text-foreground-muted">
          <Loader2 size={17} className="animate-spin text-primary motion-reduce:animate-none" aria-hidden="true" />
          Loading the current Terraform control record…
        </div>
      ) : (
        <div className="mt-5 space-y-5">
          <div className={`rounded-xl border p-4 ${stateTone}`} role={review?.status === "failed" ? "alert" : "status"}>
            <div className="flex items-start gap-3">
              <StateIcon
                size={18}
                className={`mt-0.5 shrink-0 ${stateIconTone} ${isPolling ? "animate-spin motion-reduce:animate-none" : ""}`}
                aria-hidden="true"
              />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-foreground">{state.title}</p>
                <p className="mt-1 text-xs leading-5 text-foreground-muted">
                  {review?.message || state.detail}
                </p>
                {review?.error_code && (
                  <p className="mt-2 font-mono text-[11px] text-danger">Failure code: {review.error_code}</p>
                )}
              </div>
            </div>
          </div>

          {error && (
            <div role="alert" className="rounded-xl border border-danger/25 bg-danger/10 px-4 py-3 text-xs leading-5 text-foreground">
              {error}
            </div>
          )}
          {feedback && (
            <p aria-live="polite" className="rounded-xl border border-success/25 bg-success/10 px-4 py-3 text-xs leading-5 text-foreground">
              {feedback}
            </p>
          )}

          {summary && guardrails && (
            <>
              <div className="grid gap-4 lg:grid-cols-2">
                <article className="rounded-xl border border-border bg-background p-4">
                  <h3 className="text-sm font-semibold text-foreground">Review-safe resource changes</h3>
                  <div className="mt-3 flex flex-wrap gap-2" aria-label="Terraform action counts">
                    {ACTION_KEYS.map((key) => (
                      <span key={key} className="rounded-full border border-border bg-card px-2.5 py-1 text-[11px] font-medium text-foreground-muted">
                        {ACTION_LABELS[key]} {summary.actions[key]}
                      </span>
                    ))}
                  </div>
                  {summary.changes.length > 0 ? (
                    <ul className="mt-4 divide-y divide-border rounded-lg border border-border">
                      {summary.changes.map((change) => (
                        <li key={change.address} className="grid gap-1.5 px-3 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start sm:gap-4">
                          <div className="min-w-0">
                            <p className="break-all font-mono text-xs font-semibold text-foreground">{change.address}</p>
                            <p className="mt-1 break-all font-mono text-[11px] text-foreground-muted">{change.type}</p>
                          </div>
                          <span className="w-fit rounded-full bg-primary-subtle px-2.5 py-1 text-[11px] font-semibold text-primary">
                            {change.actions.map((item) => item.replaceAll("-", " ")).join(" → ")}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-4 text-xs leading-5 text-foreground-muted">The validated plan contains no resource changes.</p>
                  )}
                </article>

                <article className="rounded-xl border border-border bg-background p-4">
                  <h3 className="text-sm font-semibold text-foreground">Target and guardrails</h3>
                  <dl className="mt-3 grid gap-3 text-xs sm:grid-cols-2">
                    <div className="sm:col-span-2">
                      <dt className="text-foreground-muted">Target resource group</dt>
                      <dd className="mt-1 break-all font-mono font-semibold text-foreground">{guardrails.target_resource_group}</dd>
                    </div>
                    <div>
                      <dt className="text-foreground-muted">Maximum changes</dt>
                      <dd className="mt-1 font-semibold tabular-nums text-foreground">{guardrails.maximum_resource_changes}</dd>
                    </div>
                    <div>
                      <dt className="text-foreground-muted">Maximum deletes / replacements</dt>
                      <dd className="mt-1 font-semibold tabular-nums text-foreground">
                        {guardrails.maximum_delete_count} / {guardrails.maximum_replace_count}
                      </dd>
                    </div>
                    <div className="sm:col-span-2">
                      <dt className="text-foreground-muted">Monthly fixed-cost budget</dt>
                      <dd className="mt-1 font-semibold tabular-nums text-foreground">
                        {guardrails.monthly_budget_microunits !== null && guardrails.budget_currency
                          ? `${formatMicrounits(guardrails.monthly_budget_microunits, guardrails.budget_currency)} per month`
                          : "No separate budget recorded"}
                      </dd>
                    </div>
                    <div className="sm:col-span-2">
                      <dt className="text-foreground-muted">Allowed resource types</dt>
                      <dd className="mt-2 flex flex-wrap gap-1.5">
                        {guardrails.allowed_resource_types.map((resourceType) => (
                          <span key={resourceType} className="break-all rounded-md border border-border bg-card px-2 py-1 font-mono text-[11px] text-foreground">
                            {resourceType}
                          </span>
                        ))}
                      </dd>
                    </div>
                  </dl>
                </article>
              </div>

              <article className="rounded-xl border border-border bg-background p-4">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-foreground">Verified exact incremental fixed cost</h3>
                    {verifiedCost ? (
                      <div className="mt-2">
                        <p className="text-xl font-semibold tabular-nums text-foreground">
                          {formatMicrounits(verifiedCost.monthly_cost_microunits, verifiedCost.currency)}
                          <span className="ml-1 text-xs font-normal text-foreground-muted">per month</span>
                        </p>
                        <p className="mt-1 text-[11px] leading-5 text-foreground-muted">
                          {verifiedCost.monthly_cost_microunits.toLocaleString()} microunits, captured {formatTimestamp(verifiedCost.captured_at)}.
                          Variable usage, traffic, bandwidth, domains, and external services are excluded.
                        </p>
                      </div>
                    ) : (
                      <p className="mt-2 text-xs leading-5 text-foreground-muted">
                        Cost evidence has not yet been bound to this saved plan.
                      </p>
                    )}
                  </div>
                  {review?.status === "awaiting_verified_cost" && (
                    <button
                      type="button"
                      onClick={() => void issueCostEvidence()}
                      disabled={interactionDisabled || !review.operation_run_id}
                      className="ops-primary min-h-11 shrink-0 px-4 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {action === "cost" ? (
                        <Loader2 size={15} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                      ) : (
                        <FileCheck2 size={15} aria-hidden="true" />
                      )}
                      {action === "cost" ? "Verifying cost" : "Verify exact cost"}
                    </button>
                  )}
                </div>
              </article>

              {exactBindings.some(([, value]) => Boolean(value)) && (
                <details className="rounded-xl border border-border bg-background p-4">
                  <summary className="min-h-11 cursor-pointer text-xs font-semibold leading-[44px] text-foreground">
                    Immutable review bindings
                  </summary>
                  <dl className="mt-2 grid gap-3">
                    {exactBindings.map(([label, value]) => (
                      <div key={label}>
                        <dt className="text-[11px] text-foreground-muted">{label}</dt>
                        <dd className="mt-1 break-all font-mono text-[11px] text-foreground">{value || "Unavailable"}</dd>
                      </div>
                    ))}
                  </dl>
                </details>
              )}
            </>
          )}

          {review?.status === "ready_for_approval" && (
            <fieldset disabled={interactionDisabled} className="rounded-xl border border-warning/30 bg-warning/10 p-4 disabled:opacity-60">
              <legend className="px-1 text-sm font-semibold text-foreground">One-time Azure apply approval</legend>
              <label htmlFor={`terraform-apply-confirm-${review.operation_run_id}`} className="mt-2 flex min-h-11 cursor-pointer items-start gap-3 text-xs leading-5 text-foreground">
                <input
                  id={`terraform-apply-confirm-${review.operation_run_id}`}
                  type="checkbox"
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.target.checked)}
                  className="mt-0.5 h-5 w-5 shrink-0 accent-[var(--primary)]"
                />
                <span>
                  I reviewed the exact resource addresses and actions, target resource group,
                  guardrails, immutable bindings, and verified incremental fixed cost above. Apply
                  this saved plan once.
                </span>
              </label>
              {!approvalRequest && (
                <p role="alert" className="mt-2 text-xs leading-5 text-danger">
                  The backend did not return a complete exact-plan approval contract. Refresh the review before continuing.
                </p>
              )}
              <button
                type="button"
                onClick={() => void approveApply()}
                disabled={!confirmed || !approvalRequest || !reviewIsCurrent || interactionDisabled}
                className="ops-primary mt-4 min-h-11 px-4 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {action === "apply" ? (
                  <Loader2 size={15} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                ) : (
                  <LockKeyhole size={15} aria-hidden="true" />
                )}
                {action === "apply" ? "Authorizing apply" : "Approve and apply once"}
              </button>
            </fieldset>
          )}

          <div className={`flex flex-col gap-4 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between ${applyProofIsCurrent ? "border-success/25 bg-success/10" : "border-border bg-background"}`}>
            <div>
              <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
                {applyProofIsCurrent ? (
                  <CheckCircle2 size={16} className="text-success" aria-hidden="true" />
                ) : (
                  <LockKeyhole size={16} className="text-foreground-muted" aria-hidden="true" />
                )}
                Application deployment
              </p>
              <p id="terraform-deployment-lock" className="mt-1 text-xs leading-5 text-foreground-muted">
                {applyProofIsCurrent
                  ? "Exact apply proof matches this revision. Deployment can now run its source, security, release, and health checks."
                  : "Start deployment unlocks only after this revision's exact Terraform apply completes successfully."}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void onStartDeployment()}
              disabled={!applyProofIsCurrent || disabled || deploymentBusy || action !== null}
              aria-describedby="terraform-deployment-lock"
              className="ops-primary min-h-11 shrink-0 px-5 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {deploymentBusy ? (
                <Loader2 size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
              ) : (
                <Rocket size={16} aria-hidden="true" />
              )}
              {deploymentBusy ? "Starting deployment" : "Start deployment"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
