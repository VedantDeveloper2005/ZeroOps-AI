"use client";

import { useMemo, useState } from "react";
import {
  AppWindow,
  BadgeCheck,
  Boxes,
  ChartNoAxesCombined,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Clock3,
  Database,
  HardDrive,
  KeyRound,
  MapPin,
  Network,
  Pencil,
  Server,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { motion } from "framer-motion";
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

const iconFor = (component: InfrastructurePlanComponent) => {
  const category = component.category.toLowerCase();
  if (category.includes("database")) return Database;
  if (category.includes("cache")) return Boxes;
  if (category.includes("storage")) return HardDrive;
  if (category.includes("secret")) return KeyRound;
  if (category.includes("network")) return Network;
  if (category.includes("monitor")) return ChartNoAxesCombined;
  return AppWindow;
};

export function InfrastructurePlan({ plan, onUpdate, onApprove, onRegenerate, busy = false }: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  const [selectedService, setSelectedService] = useState("");
  const [tier, setTier] = useState("");
  const [approvalNote, setApprovalNote] = useState("");
  const application = useMemo(() => plan.plan.components.find((component) => component.id === "application"), [plan.plan.components]);
  const canApprove = application?.service === "Azure App Service";

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
    <div className="mx-auto max-w-7xl space-y-6 pb-12">
      <section className="ops-card relative overflow-hidden rounded-3xl p-6 sm:p-8">
        <div className="ops-page-grid pointer-events-none absolute inset-0 opacity-50" />
        <div className="relative flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
          <div className="max-w-2xl">
            <span className="ops-kicker"><Sparkles size={13} /> AI CLOUD ARCHITECT</span>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <h1 className="text-balance text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">Infrastructure plan</h1>
              <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-bold ${plan.status === "approved" ? "border-success/30 bg-success/10 text-success" : "border-primary/25 bg-primary/10 text-primary"}`}>
                {plan.status === "approved" ? <CheckCircle2 size={14} /> : <Pencil size={13} />}
                {plan.status === "approved" ? "Approved" : "Review required"}
              </span>
            </div>
            <p className="mt-3 text-sm leading-6 text-foreground-muted">A source-evidence architecture for your application. Review decisions here; implementation details and credentials remain in the internal deployment engine.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:w-[360px]">
            <label className="block rounded-2xl border border-border bg-background-secondary/60 p-3">
              <span className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-[0.12em] text-foreground-muted"><MapPin size={12} /> Azure region</span>
              <span className="relative mt-2 block">
                <select
                  aria-label="Azure deployment region"
                  value={plan.region}
                  disabled={busy}
                  onChange={(event) => void onUpdate({ region: event.target.value })}
                  className="w-full appearance-none bg-transparent pr-6 text-sm font-bold text-foreground outline-none disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {regionOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
                <ChevronDown className="pointer-events-none absolute right-0 top-0.5 text-foreground-muted" size={16} />
              </span>
            </label>
            <div className="rounded-2xl border border-border bg-background-secondary/60 p-3">
              <span className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-[0.12em] text-foreground-muted"><Server size={12} /> Cloud</span>
              <p className="mt-2 text-sm font-bold text-foreground">{plan.plan.cloud} · {plan.plan.region_label}</p>
            </div>
          </div>
        </div>
      </section>

      <section aria-labelledby="plan-summary-heading">
        <h2 id="plan-summary-heading" className="sr-only">Plan validation status</h2>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <PlanSignal icon={Clock3} label="Monthly cost" value={plan.plan.cost.monthly_estimate == null ? "Awaiting validation" : `$${plan.plan.cost.monthly_estimate}/mo`} detail={plan.plan.cost.message} />
          <PlanSignal icon={Clock3} label="Deployment time" value={plan.plan.deployment_time.estimate || "Awaiting validation"} detail={plan.plan.deployment_time.message} />
          <PlanSignal icon={ShieldCheck} label="Security review" value={plan.plan.assessment.security.value == null ? "Pending" : `${plan.plan.assessment.security.value}/100`} detail="Requires Azure policy and secret configuration checks." />
          <PlanSignal icon={BadgeCheck} label="Plan revision" value={`v${plan.revision}`} detail={plan.status === "approved" ? "Ready for the deployment workflow." : "Changes require approval before deployment."} />
        </div>
      </section>

      <section aria-labelledby="resources-heading">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-primary">Recommended architecture</p>
            <h2 id="resources-heading" className="mt-1 text-xl font-bold tracking-tight text-foreground">Cloud resources and decisions</h2>
          </div>
          <p className="max-w-xl text-xs leading-5 text-foreground-muted">Every recommendation is tied to the recorded repository analysis. Services marked as configuration required are deliberately not represented as deployed resources.</p>
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {plan.plan.components.map((component, index) => {
            const Icon = iconFor(component);
            const isEditing = editing === component.id;
            return (
              <motion.article key={component.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.035 }} className="ops-card rounded-2xl p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary"><Icon size={19} /></div>
                  <div className="flex flex-wrap justify-end gap-2">
                    {component.recommended && <span className="inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-1 text-[10px] font-bold text-primary"><Sparkles size={10} /> Recommended</span>}
                    {!component.deployable && <span className="rounded-full border border-border bg-background-secondary px-2 py-1 text-[10px] font-semibold text-foreground-muted">Review setup</span>}
                  </div>
                </div>
                <p className="mt-5 text-[10px] font-extrabold uppercase tracking-[0.12em] text-foreground-muted">{component.category}</p>
                <h3 className="mt-1 text-base font-bold text-foreground">{component.service}</h3>
                <p className="mt-1 text-xs font-medium text-primary">{component.tier || "Configuration required"}</p>
                <p className="mt-4 min-h-12 text-xs leading-5 text-foreground-muted">{component.reason}</p>

                {isEditing ? (
                  <div className="mt-5 space-y-3 border-t border-border pt-4">
                    {component.available_services.length > 0 && <label className="block"><span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-foreground-muted">Service</span><select value={selectedService} onChange={(event) => setSelectedService(event.target.value)} className="min-h-11 w-full rounded-xl border border-border bg-background-secondary px-3 text-xs font-semibold text-foreground outline-none focus:border-primary"><option value={component.service}>{component.service}</option>{component.available_services.filter((service) => service !== component.service).map((service) => <option key={service} value={service}>{service}</option>)}</select></label>}
                    <label className="block"><span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-foreground-muted">Pricing tier</span><input value={tier} onChange={(event) => setTier(event.target.value)} className="min-h-11 w-full rounded-xl border border-border bg-background-secondary px-3 text-xs font-semibold text-foreground outline-none focus:border-primary" /></label>
                    <div className="flex gap-2"><button type="button" disabled={busy} onClick={() => void saveComponent(component)} className="ops-primary flex-1 px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60">Save change</button><button type="button" disabled={busy} onClick={() => setEditing(null)} className="ops-secondary px-3 text-xs disabled:opacity-60">Cancel</button></div>
                  </div>
                ) : (
                  <button type="button" disabled={busy} onClick={() => beginEdit(component)} className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-xl border border-border px-3 text-xs font-bold text-foreground transition hover:border-primary/40 hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-50"><Pencil size={14} /> Modify</button>
                )}
              </motion.article>
            );
          })}
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
        <article className="ops-card rounded-2xl p-5 sm:p-6">
          <div className="flex items-center gap-2"><ChartNoAxesCombined size={18} className="text-primary" /><h2 className="text-base font-bold text-foreground">Deployment path</h2></div>
          <ol className="mt-6 space-y-0">
            {[
              ["Repository analysis", "Completed from recorded source facts."],
              ["Architecture review", plan.status === "approved" ? "Approved by you." : "Review resource decisions and modify where needed."],
              ["Cost and resource validation", "Requires verified Azure subscription and target configuration."],
              ["Internal infrastructure preparation", "Prepared only after plan approval; source is never displayed here."],
              ["Application deployment and health checks", "Runs through the configured Azure deployment target."],
            ].map(([title, detail], index) => <li key={title} className="relative flex gap-4 pb-5 last:pb-0"><span className={`relative z-10 grid h-7 w-7 shrink-0 place-items-center rounded-full text-[11px] font-extrabold ${index < 2 || plan.status === "approved" && index === 2 ? "bg-primary text-white" : "bg-background-secondary text-foreground-muted"}`}>{index + 1}</span>{index < 4 && <span className="absolute left-[13px] top-7 h-[calc(100%-4px)] w-px bg-border" />}<div className="pt-0.5"><p className="text-sm font-bold text-foreground">{title}</p><p className="mt-1 text-xs leading-5 text-foreground-muted">{detail}</p></div></li>)}
          </ol>
        </article>

        <article className="ops-card rounded-2xl p-5 sm:p-6">
          <div className="flex items-center gap-2"><CircleAlert size={18} className="text-warning" /><h2 className="text-base font-bold text-foreground">Review before approval</h2></div>
          <p className="mt-3 text-xs leading-5 text-foreground-muted">{plan.plan.assessment.readiness_message}</p>
          {plan.plan.assessment.source_findings.length > 0 && <div className="mt-4 rounded-xl border border-warning/20 bg-warning/10 p-3"><p className="text-xs font-bold text-foreground">Source findings</p><ul className="mt-2 space-y-1.5 text-xs leading-5 text-foreground-muted">{plan.plan.assessment.source_findings.map((finding) => <li key={finding}>• {finding}</li>)}</ul></div>}
          {plan.status !== "approved" ? <div className="mt-5"><label className="block"><span className="mb-1.5 block text-xs font-bold text-foreground">Approval note <span className="font-normal text-foreground-muted">(optional)</span></span><textarea value={approvalNote} onChange={(event) => setApprovalNote(event.target.value)} maxLength={500} placeholder="Any constraints the deployment team should know?" className="min-h-24 w-full rounded-xl border border-border bg-background-secondary p-3 text-xs leading-5 text-foreground outline-none placeholder:text-foreground-muted focus:border-primary" /></label>{!canApprove && <p className="mt-2 text-xs leading-5 text-warning">This architecture uses a target that is not enabled for deployment in this workspace. Select Azure App Service to approve it.</p>}<button type="button" disabled={busy || !canApprove} onClick={() => void onApprove(approvalNote)} className="ops-primary mt-4 w-full px-4 text-sm disabled:cursor-not-allowed disabled:opacity-50"><CheckCircle2 size={16} /> Approve architecture plan</button></div> : <div className="mt-5 rounded-xl border border-success/25 bg-success/10 p-4"><div className="flex items-center gap-2 text-success"><CheckCircle2 size={17} /><p className="text-sm font-bold">Plan approved</p></div><p className="mt-1.5 text-xs leading-5 text-foreground-muted">The deployment workflow will use revision {plan.revision}. Any modification creates a new draft for your approval.</p></div>}
          {plan.status !== "approved" && <button type="button" disabled={busy} onClick={() => void onRegenerate()} className="mt-3 w-full text-center text-xs font-bold text-primary underline-offset-4 transition hover:underline disabled:opacity-50">Regenerate from latest analysis</button>}
        </article>
      </section>
    </div>
  );
}

function PlanSignal({ icon: Icon, label, value, detail }: { icon: typeof Clock3; label: string; value: string; detail: string }) {
  return <article className="ops-card rounded-2xl p-5"><Icon size={18} className="text-primary" /><p className="mt-4 text-[10px] font-extrabold uppercase tracking-[0.12em] text-foreground-muted">{label}</p><p className="mt-1.5 text-base font-bold text-foreground">{value}</p><p className="mt-2 text-[11px] leading-4 text-foreground-muted">{detail}</p></article>;
}
