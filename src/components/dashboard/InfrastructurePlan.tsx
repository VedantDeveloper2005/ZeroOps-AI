"use client";

import { useMemo, useState } from "react";
import {
  AppWindow,
  BadgeCheck,
  Boxes,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Database,
  HardDrive,
  KeyRound,
  Loader2,
  MapPin,
  Network,
  Pencil,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import type {
  InfrastructurePlan as InfrastructurePlanModel,
  InfrastructurePlanComponent,
  InfrastructurePlanUpdate,
} from "@/lib/api";

type Props = {
  plan: InfrastructurePlanModel;
  onUpdate: (update: InfrastructurePlanUpdate) => Promise<boolean>;
  onApprove: (note?: string) => Promise<boolean>;
  onRegenerate: () => Promise<boolean>;
  busy?: boolean;
};

const regionOptions = [
  { value: "centralindia", label: "Central India" },
  { value: "eastus", label: "East US" },
  { value: "westeurope", label: "West Europe" },
  { value: "uksouth", label: "UK South" },
  { value: "southeastasia", label: "Southeast Asia" },
];

function iconFor(component: InfrastructurePlanComponent) {
  const category = component.category.toLowerCase();
  if (category.includes("database")) return Database;
  if (category.includes("cache")) return Boxes;
  if (category.includes("storage")) return HardDrive;
  if (category.includes("secret")) return KeyRound;
  if (category.includes("network")) return Network;
  return AppWindow;
}

export function InfrastructurePlan({
  plan,
  onUpdate,
  onApprove,
  onRegenerate,
  busy = false,
}: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  const [selectedService, setSelectedService] = useState("");
  const [tier, setTier] = useState("");
  const [approvalNote, setApprovalNote] = useState("");
  const [confirmRegenerate, setConfirmRegenerate] = useState(false);

  const application = useMemo(
    () => plan.plan.components.find((component) => component.id === "application"),
    [plan.plan.components],
  );
  const canApprove = application?.service === "Azure App Service";
  const evidence = plan.plan.application_evidence;
  const sourceFindings = (plan.plan.assessment.source_findings ?? []).filter(
    (finding) => !/checks? passed successfully/i.test(finding),
  );
  const unresolvedQuestions = plan.plan.assessment.unresolved_questions ?? [];
  const selectedRegionIsKnown = regionOptions.some((option) => option.value === plan.region);

  const beginEdit = (component: InfrastructurePlanComponent) => {
    setEditing(component.id);
    setSelectedService(component.service);
    setTier(component.tier || "");
  };

  const saveComponent = async (component: InfrastructurePlanComponent) => {
    const serviceChanged = selectedService !== component.service;
    const tierChanged = tier.trim() !== (component.tier || "");
    if (!serviceChanged && !tierChanged) {
      setEditing(null);
      return;
    }

    const updated = await onUpdate({
      component_id: component.id,
      service: serviceChanged ? selectedService : undefined,
      tier: tierChanged ? tier.trim() : undefined,
    });
    if (updated) {
      setEditing(null);
    }
  };

  const regenerate = async () => {
    const regenerated = await onRegenerate();
    if (regenerated) {
      setConfirmRegenerate(false);
    }
  };

  return (
    <div className="space-y-5 pb-2">
      <section aria-labelledby="plan-heading" className="ops-card rounded-2xl p-5 sm:p-7">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-2xl">
            <p className="text-xs font-semibold text-primary">Saved infrastructure proposal</p>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <h2
                id="plan-heading"
                className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl"
              >
                Azure plan revision {plan.revision}
              </h2>
              <StatusBadge status={plan.status} />
            </div>
            <p className="mt-3 text-sm leading-6 text-foreground-muted">
              This proposal is derived from recorded repository analysis. It is not a live Azure
              inventory, a price quote, a performance test, or a security certification.
            </p>
          </div>

          <label className="rounded-xl border border-border bg-background-secondary/55 px-3 py-2.5 lg:w-72">
            <span className="flex items-center gap-1.5 text-xs font-medium text-foreground-muted">
              <MapPin size={14} aria-hidden="true" /> Proposed Azure region
            </span>
            <span className="relative mt-1.5 block">
              <select
                aria-describedby="region-change-note"
                value={plan.region}
                disabled={busy}
                onChange={(event) => void onUpdate({ region: event.target.value })}
                className="min-h-9 w-full appearance-none bg-transparent pr-7 text-sm font-semibold text-foreground outline-none disabled:cursor-not-allowed disabled:opacity-60"
              >
                {!selectedRegionIsKnown && <option value={plan.region}>{plan.region}</option>}
                {regionOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <ChevronDown
                className="pointer-events-none absolute right-0 top-2 text-foreground-muted"
                size={16}
                aria-hidden="true"
              />
            </span>
            <span
              id="region-change-note"
              className="mt-1 block text-[11px] leading-4 text-foreground-muted"
            >
              A change creates a new revision and requires approval again.
            </span>
          </label>
        </div>
      </section>

      <section aria-labelledby="evidence-heading">
        <h2 id="evidence-heading" className="sr-only">
          Recorded plan evidence
        </h2>
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <EvidenceItem label="Cloud target" value={plan.plan.cloud || "Azure"} />
          <EvidenceItem label="Framework" value={evidence.framework || "Not detected"} />
          <EvidenceItem label="Runtime" value={evidence.runtime || "Not detected"} />
          <EvidenceItem
            label="Package manager"
            value={evidence.package_manager || "Not detected"}
          />
        </dl>
      </section>

      <aside
        aria-label="Validation boundaries"
        className="rounded-xl border border-warning/25 bg-warning/10 p-4"
      >
        <div className="flex items-start gap-3">
          <CircleAlert
            size={18}
            className="mt-0.5 shrink-0 text-warning"
            aria-hidden="true"
          />
          <div>
            <p className="text-sm font-semibold text-foreground">
              Cost and runtime outcomes are not estimated here
            </p>
            <p className="mt-1 text-xs leading-5 text-foreground-muted">
              Subscription-specific pricing, deployment duration, performance, and reliability
              require Azure-side validation or runtime telemetry. No synthetic scores or costs are
              shown.
            </p>
          </div>
        </div>
      </aside>

      <section aria-labelledby="resources-heading">
        <div className="mb-3 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold text-primary">Proposed resources</p>
            <h2
              id="resources-heading"
              className="mt-1 text-lg font-semibold tracking-tight text-foreground"
            >
              Architecture decisions
            </h2>
          </div>
          <p className="max-w-xl text-xs leading-5 text-foreground-muted">
            The reason under each resource comes from the saved plan. Azure availability and
            permissions are validated later by the deployment workflow.
          </p>
        </div>

        <div className="ops-card overflow-hidden rounded-2xl">
          {plan.plan.components.map((component) => {
            const Icon = iconFor(component);
            const isEditing = editing === component.id;
            const serviceChanged = selectedService !== component.service;
            const tierChanged = tier.trim() !== (component.tier || "");
            const hasChanges = serviceChanged || tierChanged;

            return (
              <article
                key={component.id}
                className="border-b border-border p-4 last:border-b-0 sm:p-5"
              >
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="flex min-w-0 gap-3">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
                      <Icon size={18} aria-hidden="true" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <h3 className="text-sm font-semibold text-foreground">
                          {component.service}
                        </h3>
                        {component.recommended && (
                          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">
                            Proposed
                          </span>
                        )}
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                            component.deployable
                              ? "bg-success/10 text-success"
                              : "bg-background-secondary text-foreground-muted"
                          }`}
                        >
                          {component.deployable
                            ? "Supported by current engine"
                            : "Not deployable here"}
                        </span>
                      </div>
                      <p className="mt-1 text-xs font-medium text-primary">
                        {component.category}
                        {component.tier ? ` · ${component.tier}` : ""}
                      </p>
                      <p className="mt-2 max-w-3xl text-xs leading-5 text-foreground-muted">
                        {component.reason}
                      </p>
                    </div>
                  </div>
                  {!isEditing && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => beginEdit(component)}
                      className="ops-secondary min-h-11 shrink-0 px-3 text-xs disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Pencil size={14} aria-hidden="true" /> Modify
                    </button>
                  )}
                </div>

                {isEditing && (
                  <div className="mt-4 grid gap-3 border-t border-border pt-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
                    <label className="block">
                      <span className="mb-1 block text-xs font-medium text-foreground-muted">
                        Service
                      </span>
                      <select
                        value={selectedService}
                        disabled={busy || component.available_services.length === 0}
                        onChange={(event) => setSelectedService(event.target.value)}
                        className="min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <option value={component.service}>{component.service}</option>
                        {component.available_services
                          .filter((service) => service !== component.service)
                          .map((service) => (
                            <option key={service} value={service}>
                              {service}
                            </option>
                          ))}
                      </select>
                      {component.available_services.length === 0 && (
                        <span className="mt-1 block text-[11px] leading-4 text-foreground-muted">
                          No alternative service is configured for this resource.
                        </span>
                      )}
                    </label>
                    <label className="block">
                      <span className="mb-1 block text-xs font-medium text-foreground-muted">
                        Proposed tier
                      </span>
                      <input
                        value={tier}
                        disabled={busy}
                        onChange={(event) => setTier(event.target.value)}
                        className="min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60"
                      />
                      <span className="mt-1 block text-[11px] leading-4 text-foreground-muted">
                        Availability and pricing are validated against Azure later.
                      </span>
                    </label>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        disabled={busy || !hasChanges || !tier.trim()}
                        onClick={() => void saveComponent(component)}
                        className="ops-primary min-h-11 flex-1 px-3 text-xs disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {busy && <Loader2 size={14} className="animate-spin" aria-hidden="true" />}
                        Save
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => setEditing(null)}
                        className="ops-secondary min-h-11 px-3 text-xs disabled:opacity-60"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-[0.85fr_1.15fr]">
        <article className="ops-card rounded-2xl p-5">
          <div className="flex items-center gap-2">
            <ShieldCheck size={18} className="text-primary" aria-hidden="true" />
            <h2 className="text-base font-semibold text-foreground">Execution boundary</h2>
          </div>
          <ol className="mt-5 space-y-4 text-xs leading-5 text-foreground-muted">
            <WorkflowStep
              number={1}
              title="Review this revision"
              detail="Confirm the proposed service, region, tier text, and recorded source findings."
            />
            <WorkflowStep
              number={2}
              title="Approve explicitly"
              detail="Approval applies only to this revision. Any edit returns the plan to draft."
            />
            <WorkflowStep
              number={3}
              title="Start the deployment"
              detail="The deployment endpoint reruns prerequisites before it can create or update resources."
            />
            <WorkflowStep
              number={4}
              title="Inspect the recorded outcome"
              detail="Use persisted deployment logs and the verified release URL to determine what actually happened."
            />
          </ol>
        </article>

        <article className="ops-card rounded-2xl p-5">
          <div className="flex items-center gap-2">
            <BadgeCheck size={18} className="text-primary" aria-hidden="true" />
            <h2 className="text-base font-semibold text-foreground">Review and approval</h2>
          </div>
          <p className="mt-3 text-xs leading-5 text-foreground-muted">
            This workspace currently executes Azure App Service application plans. Other services
            can be recorded for review but are not deployable by the current engine.
          </p>

          {(sourceFindings.length > 0 || unresolvedQuestions.length > 0) && (
            <details className="mt-4 rounded-xl border border-warning/25 bg-warning/10 p-3">
              <summary className="flex min-h-11 cursor-pointer items-center text-xs font-semibold text-foreground">
                Review recorded analysis notes
              </summary>
              <div className="mt-3 space-y-4">
                {sourceFindings.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-foreground">
                      Automated source findings
                    </p>
                    <ul className="mt-2 list-disc space-y-2 pl-5 text-xs leading-5 text-foreground-muted">
                      {sourceFindings.map((finding) => (
                        <li key={finding}>{finding}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {unresolvedQuestions.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-foreground">Open questions</p>
                    <ul className="mt-2 list-disc space-y-2 pl-5 text-xs leading-5 text-foreground-muted">
                      {unresolvedQuestions.map((question) => (
                        <li key={question}>{question}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <p className="text-[11px] leading-4 text-foreground-muted">
                  Automated findings require human verification before a production release.
                </p>
              </div>
            </details>
          )}

          {plan.status === "draft" ? (
            <div className="mt-5">
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-foreground">
                  Approval note{" "}
                  <span className="font-normal text-foreground-muted">(optional)</span>
                </span>
                <textarea
                  value={approvalNote}
                  onChange={(event) => setApprovalNote(event.target.value)}
                  maxLength={500}
                  placeholder="Record constraints or review context for this revision."
                  className="min-h-24 w-full rounded-xl border border-border bg-background p-3 text-sm leading-5 text-foreground outline-none placeholder:text-foreground-muted focus:border-primary focus:ring-2 focus:ring-primary/15"
                />
                <span className="mt-1 block text-right text-[11px] text-foreground-muted">
                  {approvalNote.length}/500
                </span>
              </label>

              {!canApprove && (
                <p className="mt-2 text-xs leading-5 text-warning">
                  Select Azure App Service for the application before approving this plan.
                </p>
              )}

              <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                {confirmRegenerate ? (
                  <div
                    role="group"
                    aria-label="Confirm plan regeneration"
                    className="rounded-xl border border-warning/25 bg-warning/10 p-3"
                  >
                    <p className="max-w-sm text-xs leading-5 text-foreground">
                      Regenerating replaces manual edits with a new proposal from the latest saved
                      analysis.
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void regenerate()}
                        className="ops-secondary min-h-11 px-3 text-xs disabled:opacity-50"
                      >
                        <RotateCcw size={14} aria-hidden="true" />
                        Confirm regenerate
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => setConfirmRegenerate(false)}
                        className="min-h-11 px-3 text-xs font-semibold text-foreground-muted hover:text-foreground disabled:opacity-50"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => setConfirmRegenerate(true)}
                    className="min-h-11 w-fit px-1 text-left text-xs font-semibold text-primary disabled:opacity-50"
                  >
                    Regenerate from saved analysis
                  </button>
                )}

                <button
                  type="button"
                  disabled={busy || !canApprove}
                  onClick={() => void onApprove(approvalNote)}
                  className="ops-primary min-h-11 shrink-0 px-4 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busy ? (
                    <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                  ) : (
                    <CheckCircle2 size={16} aria-hidden="true" />
                  )}
                  Approve revision {plan.revision}
                </button>
              </div>
            </div>
          ) : (
            <div className="mt-5 rounded-xl border border-success/25 bg-success/10 p-4">
              <div className="flex items-center gap-2 text-success">
                <CheckCircle2 size={17} aria-hidden="true" />
                <p className="text-sm font-semibold">
                  {plan.status === "approved"
                    ? "This revision is approved"
                    : "This revision has entered the deployment workflow"}
                </p>
              </div>
              <p className="mt-1.5 text-xs leading-5 text-foreground-muted">
                {plan.approval_note
                  ? `Recorded note: ${plan.approval_note}`
                  : `Approval is recorded for revision ${plan.revision}.`}
              </p>
            </div>
          )}
        </article>
      </section>
    </div>
  );
}

function StatusBadge({ status }: { status: InfrastructurePlanModel["status"] }) {
  const styles = {
    draft: "border-primary/20 bg-primary/10 text-primary",
    approved: "border-success/25 bg-success/10 text-success",
    provisioning: "border-warning/25 bg-warning/10 text-warning",
    deployed: "border-success/25 bg-success/10 text-success",
  } as const;
  const labels = {
    draft: "Review required",
    approved: "Approved",
    provisioning: "Deployment in progress",
    deployed: "Deployed",
  } as const;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${styles[status]}`}
    >
      {status === "draft" ? (
        <Pencil size={13} aria-hidden="true" />
      ) : (
        <CheckCircle2 size={13} aria-hidden="true" />
      )}
      {labels[status]}
    </span>
  );
}

function EvidenceItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-card px-4 py-3.5">
      <dt className="text-xs font-medium text-foreground-muted">{label}</dt>
      <dd className="mt-1.5 break-words text-sm font-semibold text-foreground">{value}</dd>
    </div>
  );
}

function WorkflowStep({
  number,
  title,
  detail,
}: {
  number: number;
  title: string;
  detail: string;
}) {
  return (
    <li className="flex gap-3">
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
        {number}
      </span>
      <div>
        <p className="font-semibold text-foreground">{title}</p>
        <p className="mt-0.5">{detail}</p>
      </div>
    </li>
  );
}
