"use client";

import { useMemo, useState } from "react";
import {
  AppWindow,
  ArrowRight,
  BadgeCheck,
  Boxes,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Database,
  HardDrive,
  KeyRound,
  MapPin,
  Network,
  Pencil,
} from "lucide-react";
import type { InfrastructurePlan as InfrastructurePlanModel, InfrastructurePlanComponent, InfrastructurePlanUpdate } from "@/lib/api";

type Props = {
  plan: InfrastructurePlanModel;
  onUpdate: (update: InfrastructurePlanUpdate) => Promise<void>;
  onApprove: (note?: string) => Promise<void>;
  onRegenerate: () => Promise<void>;
  busy?: boolean;
};

const regionOptions = [
  { value: "centralindia", label: "Central India" },
  { value: "eastus", label: "East US" },
  { value: "westeurope", label: "West Europe" },
  { value: "uksouth", label: "UK South" },
  { value: "southeastasia", label: "Southeast Asia" },
];

const deploymentSteps = [
  "Repository analysis",
  "Architecture review",
  "Preflight validation",
  "Internal preparation",
  "Deploy and health check",
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

export function InfrastructurePlan({ plan, onUpdate, onApprove, onRegenerate, busy = false }: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  const [selectedService, setSelectedService] = useState("");
  const [tier, setTier] = useState("");
  const [approvalNote, setApprovalNote] = useState("");
  const application = useMemo(
    () => plan.plan.components.find((component) => component.id === "application"),
    [plan.plan.components],
  );
  const canApprove = application?.service === "Azure App Service";
  const sourceFindings = plan.plan.assessment.source_findings;

  const beginEdit = (component: InfrastructurePlanComponent) => {
    setEditing(component.id);
    setSelectedService(component.service);
    setTier(component.tier || "");
  };

  const saveComponent = async (component: InfrastructurePlanComponent) => {
    await onUpdate({
      component_id: component.id,
      service: selectedService === component.service ? undefined : selectedService,
      tier: tier === component.tier ? undefined : tier,
    });
    setEditing(null);
  };

  return (
    <div className="mx-auto max-w-7xl space-y-5 pb-8">
      <section className="ops-card rounded-2xl p-5 sm:p-7">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-2xl">
            <p className="text-xs font-semibold text-primary">Architecture plan</p>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">A clear path to deployment</h1>
              <StatusBadge approved={plan.status === "approved"} />
            </div>
            <p className="mt-3 text-sm leading-6 text-foreground-muted">Review the recommended services, make any change you need, then approve this exact plan. Implementation details and credentials stay protected.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:w-[360px]">
            <label className="rounded-xl border border-border bg-background-secondary/55 px-3 py-2.5">
              <span className="flex items-center gap-1.5 text-xs font-medium text-foreground-muted"><MapPin size={14} /> Region</span>
              <span className="relative mt-1.5 block">
                <select
                  aria-label="Azure deployment region"
                  value={plan.region}
                  disabled={busy}
                  onChange={(event) => void onUpdate({ region: event.target.value })}
                  className="min-h-8 w-full appearance-none bg-transparent pr-6 text-sm font-semibold text-foreground outline-none disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {regionOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
                <ChevronDown className="pointer-events-none absolute right-0 top-1 text-foreground-muted" size={16} />
              </span>
            </label>
            <div className="rounded-xl border border-border bg-background-secondary/55 px-3 py-2.5">
              <p className="text-xs font-medium text-foreground-muted">Cloud</p>
              <p className="mt-2 text-sm font-semibold text-foreground">{plan.plan.cloud} · {plan.plan.region_label}</p>
            </div>
          </div>
        </div>
      </section>

      <section aria-labelledby="plan-summary-heading" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <h2 id="plan-summary-heading" className="sr-only">Plan summary</h2>
        <SummaryItem label="Monthly cost" value={plan.plan.cost.monthly_estimate == null ? "Awaiting validation" : `$${plan.plan.cost.monthly_estimate}/mo`} detail={plan.plan.cost.message} />
        <SummaryItem label="Deployment time" value={plan.plan.deployment_time.estimate || "Awaiting validation"} detail={plan.plan.deployment_time.message} />
        <SummaryItem label="Security review" value={plan.plan.assessment.security.value == null ? "Pending" : `${plan.plan.assessment.security.value}/100`} detail="Validated by policy, secret, and target checks." />
        <SummaryItem label="Plan revision" value={`v${plan.revision}`} detail={plan.status === "approved" ? "This revision is approved." : "Changes require approval."} />
      </section>

      <section aria-labelledby="resources-heading">
        <div className="mb-3 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold text-primary">Recommended services</p>
            <h2 id="resources-heading" className="mt-1 text-lg font-semibold tracking-tight text-foreground">Architecture decisions</h2>
          </div>
          <p className="max-w-xl text-xs leading-5 text-foreground-muted">Each recommendation is linked to recorded application evidence. Services marked “setup needed” are not provisioned automatically.</p>
        </div>

        <div className="ops-card overflow-hidden rounded-2xl">
          {plan.plan.components.map((component) => {
            const Icon = iconFor(component);
            const isEditing = editing === component.id;
            return (
              <article key={component.id} className="border-b border-border p-4 last:border-b-0 sm:p-5">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="flex min-w-0 gap-3">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary"><Icon size={18} /></div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <h3 className="text-sm font-semibold text-foreground">{component.service}</h3>
                        {component.recommended && <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">Recommended</span>}
                        {!component.deployable && <span className="rounded-full bg-background-secondary px-2 py-0.5 text-[10px] font-medium text-foreground-muted">Setup needed</span>}
                      </div>
                      <p className="mt-1 text-xs font-medium text-primary">{component.category}{component.tier ? ` · ${component.tier}` : ""}</p>
                      <p className="mt-2 max-w-3xl text-xs leading-5 text-foreground-muted">{component.reason}</p>
                    </div>
                  </div>
                  {!isEditing && <button type="button" disabled={busy} onClick={() => beginEdit(component)} className="ops-secondary shrink-0 px-3 text-xs disabled:cursor-not-allowed disabled:opacity-50"><Pencil size={14} /> Modify</button>}
                </div>

                {isEditing && <div className="mt-4 grid gap-3 border-t border-border pt-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
                  {component.available_services.length > 0 && <label className="block"><span className="mb-1 block text-xs font-medium text-foreground-muted">Service</span><select value={selectedService} onChange={(event) => setSelectedService(event.target.value)} className="min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary"><option value={component.service}>{component.service}</option>{component.available_services.filter((service) => service !== component.service).map((service) => <option key={service} value={service}>{service}</option>)}</select></label>}
                  <label className="block"><span className="mb-1 block text-xs font-medium text-foreground-muted">Pricing tier</span><input value={tier} onChange={(event) => setTier(event.target.value)} className="min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary" /></label>
                  <div className="flex gap-2"><button type="button" disabled={busy} onClick={() => void saveComponent(component)} className="ops-primary flex-1 px-3 text-xs disabled:opacity-60">Save</button><button type="button" disabled={busy} onClick={() => setEditing(null)} className="ops-secondary px-3 text-xs disabled:opacity-60">Cancel</button></div>
                </div>}
              </article>
            );
          })}
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
        <article className="ops-card rounded-2xl p-5">
          <div className="flex items-center gap-2"><BadgeCheck size={18} className="text-primary" /><h2 className="text-base font-semibold text-foreground">What happens next</h2></div>
          <ol className="mt-5 space-y-3">
            {deploymentSteps.map((step, index) => {
              const complete = index === 0 || (index === 1 && plan.status === "approved");
              return <li key={step} className="flex items-center gap-3"><span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-[11px] font-semibold ${complete ? "bg-primary text-white" : "bg-background-secondary text-foreground-muted"}`}>{complete ? <CheckCircle2 size={14} /> : index + 1}</span><span className={`text-xs ${complete ? "font-medium text-foreground" : "text-foreground-muted"}`}>{step}</span>{index < deploymentSteps.length - 1 && <ArrowRight size={13} className="ml-auto text-foreground-muted/55" />}</li>;
            })}
          </ol>
        </article>

        <article className="ops-card rounded-2xl p-5">
          <div className="flex items-center gap-2"><CircleAlert size={18} className="text-warning" /><h2 className="text-base font-semibold text-foreground">Review and approval</h2></div>
          <p className="mt-3 text-xs leading-5 text-foreground-muted">{plan.plan.assessment.readiness_message}</p>
          {sourceFindings.length > 0 && <details className="mt-4 rounded-xl border border-warning/20 bg-warning/10 p-3"><summary className="cursor-pointer text-xs font-semibold text-foreground">{sourceFindings.length} source finding{sourceFindings.length === 1 ? "" : "s"} to review</summary><ul className="mt-3 space-y-2 text-xs leading-5 text-foreground-muted">{sourceFindings.map((finding) => <li key={finding} className="flex gap-2"><span aria-hidden="true">•</span><span>{finding}</span></li>)}</ul></details>}
          {plan.status !== "approved" ? <div className="mt-5"><label className="block"><span className="mb-1.5 block text-xs font-medium text-foreground">Approval note <span className="font-normal text-foreground-muted">(optional)</span></span><textarea value={approvalNote} onChange={(event) => setApprovalNote(event.target.value)} maxLength={500} placeholder="Add any deployment constraints." className="min-h-24 w-full rounded-xl border border-border bg-background p-3 text-sm leading-5 text-foreground outline-none placeholder:text-foreground-muted focus:border-primary" /></label>{!canApprove && <p className="mt-2 text-xs leading-5 text-warning">Select Azure App Service before this workspace can approve the plan.</p>}<div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-between"><button type="button" disabled={busy} onClick={() => void onRegenerate()} className="min-h-11 px-2 text-left text-xs font-semibold text-primary disabled:opacity-50">Regenerate from analysis</button><button type="button" disabled={busy || !canApprove} onClick={() => void onApprove(approvalNote)} className="ops-primary px-4 text-sm disabled:cursor-not-allowed disabled:opacity-50"><CheckCircle2 size={16} /> Approve plan</button></div></div> : <div className="mt-5 rounded-xl border border-success/25 bg-success/10 p-4"><div className="flex items-center gap-2 text-success"><CheckCircle2 size={17} /><p className="text-sm font-semibold">Plan approved</p></div><p className="mt-1.5 text-xs leading-5 text-foreground-muted">Deployment will use revision {plan.revision}. Editing it creates a new plan for your approval.</p></div>}
        </article>
      </section>
    </div>
  );
}

function StatusBadge({ approved }: { approved: boolean }) {
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${approved ? "border-success/25 bg-success/10 text-success" : "border-primary/20 bg-primary/10 text-primary"}`}>{approved ? <CheckCircle2 size={13} /> : <Pencil size={13} />}{approved ? "Approved" : "Review needed"}</span>;
}

function SummaryItem({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <article className="rounded-xl border border-border bg-card px-4 py-3.5"><p className="text-xs font-medium text-foreground-muted">{label}</p><p className="mt-1.5 text-sm font-semibold text-foreground">{value}</p><p className="mt-1.5 text-xs leading-4 text-foreground-muted">{detail}</p></article>;
}
