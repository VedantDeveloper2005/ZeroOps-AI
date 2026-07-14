"use client";

import {
  Activity,
  BrainCircuit,
  CheckCircle2,
  CircleAlert,
  GitBranch,
  Loader2,
  Network,
  Play,
  ShieldCheck,
  Target,
  XCircle,
} from "lucide-react";
import type { DecisionAccuracy, DigitalTwinSimulation, KnowledgeGraph } from "@/lib/api";

type Props = {
  graph: KnowledgeGraph | null;
  simulation: DigitalTwinSimulation | null;
  accuracy: DecisionAccuracy | null;
  loading?: boolean;
  onRunSimulation: () => Promise<void>;
};

const stateStyle = {
  ready: "border-success/25 bg-success/10 text-success",
  requires_review: "border-warning/25 bg-warning/10 text-warning",
  blocked: "border-danger/25 bg-danger/10 text-danger",
} as const;

const checkStyle = {
  passed: "text-success",
  warning: "text-warning",
  blocked: "text-danger",
} as const;

function checkIcon(status: "passed" | "warning" | "blocked") {
  if (status === "passed") return CheckCircle2;
  if (status === "warning") return CircleAlert;
  return XCircle;
}

export function DecisionIntelligencePanel({ graph, simulation, accuracy, loading = false, onRunSimulation }: Props) {
  const labels = new Map(graph?.graph.nodes.map((node) => [node.id, node.label]) || []);
  const visibleEdges = (graph?.graph.edges || []).slice(0, 6);

  return (
    <section aria-labelledby="decision-intelligence-heading" className="mx-auto max-w-7xl space-y-5">
      <div className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div>
          <p className="text-[10px] font-extrabold uppercase tracking-[0.13em] text-primary">Controlled decision pipeline</p>
          <h2 id="decision-intelligence-heading" className="mt-1 text-xl font-bold tracking-tight text-foreground">Decision intelligence</h2>
          <p className="mt-2 max-w-2xl text-xs leading-5 text-foreground-muted">Evidence graph, deterministic risk policy, explicit approval, and observed deployment outcomes. The preflight reads recorded data only and does not change Azure.</p>
        </div>
        <button type="button" disabled={loading} onClick={() => void onRunSimulation()} className="ops-primary min-h-11 shrink-0 px-4 text-sm disabled:cursor-not-allowed disabled:opacity-60">
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />} {loading ? "Running preflight" : "Run digital-twin preflight"}
        </button>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <article className="ops-card rounded-2xl p-5 sm:p-6">
          <div className="flex items-start justify-between gap-3">
            <div><div className="flex items-center gap-2"><Activity size={18} className="text-primary" /><h3 className="text-base font-bold text-foreground">Digital twin simulation</h3></div><p className="mt-2 text-xs leading-5 text-foreground-muted">A non-mutating structural preflight of the selected architecture and available Azure target.</p></div>
            {simulation && <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wide ${stateStyle[simulation.status]}`}>{simulation.status.replaceAll("_", " ")}</span>}
          </div>
          {simulation ? <>
            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              <Metric label="Risk score" value={`${simulation.risk_score}/100`} detail={simulation.risk_level} />
              <Metric label="Plan revision" value={`v${simulation.plan_revision ?? "—"}`} detail={simulation.model} />
              <Metric label="Azure target" value={simulation.snapshot.target_ready ? "Ready" : "Not ready"} detail={simulation.snapshot.application_service || "No app service selected"} />
            </div>
            <p className="mt-4 rounded-xl border border-border bg-background-secondary/50 p-3 text-xs leading-5 text-foreground-muted">{simulation.summary}</p>
            <div className="mt-5 space-y-3">
              {simulation.checks.map((check) => {
                const Icon = checkIcon(check.status);
                return <div key={check.id} className="flex gap-3 rounded-xl border border-border/80 px-3 py-3"><Icon size={17} className={`mt-0.5 shrink-0 ${checkStyle[check.status]}`} /><div className="min-w-0"><p className="text-xs font-bold text-foreground">{check.label}{check.risk_weight > 0 && <span className="ml-2 font-medium text-foreground-muted">+{check.risk_weight} risk</span>}</p><p className="mt-1 text-[11px] leading-4 text-foreground-muted">{check.detail}</p></div></div>;
              })}
            </div>
          </> : <EmptyState icon={Target} message="No preflight is recorded yet. Run it to validate the plan without provisioning resources." />}
        </article>

        <div className="space-y-5">
          <article className="ops-card rounded-2xl p-5">
            <div className="flex items-center gap-2"><Network size={18} className="text-primary" /><h3 className="text-base font-bold text-foreground">Knowledge graph</h3></div>
            <p className="mt-2 text-xs leading-5 text-foreground-muted">An auditable relationship map from repository facts to architecture choices. Configuration references are names only; values are never included.</p>
            {graph ? <>
              <div className="mt-4 grid grid-cols-2 gap-3"><Metric label="Nodes" value={String(graph.graph.nodes.length)} detail={`Plan v${graph.plan_revision ?? "—"}`} /><Metric label="Relations" value={String(graph.graph.edges.length)} detail="Evidence-linked" /></div>
              <div className="mt-4 space-y-2">
                {visibleEdges.map((edge, index) => <div key={`${edge.source}-${edge.target}-${index}`} className="flex items-center gap-2 text-[11px] leading-4"><GitBranch size={14} className="shrink-0 text-primary" /><span className="min-w-0 truncate font-semibold text-foreground">{labels.get(edge.source) || "Source"}</span><span className="shrink-0 text-foreground-muted">{edge.relation.replaceAll("_", " ")} →</span><span className="min-w-0 truncate text-foreground-muted">{labels.get(edge.target) || "Target"}</span></div>)}
              </div>
            </> : <EmptyState icon={Network} message="The graph is created with the architecture plan and refreshed from recorded source evidence." />}
          </article>

          <article className="ops-card rounded-2xl p-5">
            <div className="flex items-center gap-2"><BrainCircuit size={18} className="text-primary" /><h3 className="text-base font-bold text-foreground">Measured decision accuracy</h3></div>
            {accuracy?.available ? <><p className="mt-4 text-3xl font-extrabold tracking-tight text-foreground">{accuracy.outcome_accuracy_percent}%</p><p className="mt-1 text-xs text-foreground-muted">{accuracy.successful_deployments} successful of {accuracy.evaluated_deployments} evaluated deployment decision{accuracy.evaluated_deployments === 1 ? "" : "s"}.</p></> : <p className="mt-4 text-sm font-semibold text-foreground">No evaluated deployments yet</p>}
            <p className="mt-3 text-[11px] leading-4 text-foreground-muted">{accuracy?.methodology || "Accuracy is shown only after a deployment reaches a real health-validated terminal outcome."}</p>
          </article>
        </div>
      </div>

      <article className="rounded-2xl border border-primary/20 bg-primary/5 p-5 sm:p-6">
        <div className="flex items-center gap-2"><ShieldCheck size={18} className="text-primary" /><h3 className="text-base font-bold text-foreground">How the safeguard works</h3></div>
        <div className="mt-4 grid gap-4 text-xs leading-5 text-foreground-muted md:grid-cols-3">
          <p><span className="font-bold text-foreground">Grounded decisions.</span> Recommendations use persisted scan evidence and explicit unknowns; generated language cannot directly execute an infrastructure change.</p>
          <p><span className="font-bold text-foreground">Human control.</span> Architecture changes invalidate approval. Execution requires a new user approval, a non-mutating preflight, a connected target, and internal engine validation.</p>
          <p><span className="font-bold text-foreground">Wrong-decision containment.</span> Blocking checks stop execution before provisioning. A deployment failure is recorded, linked to its decision, and analyzed; no autonomous retry or remediation is triggered.</p>
        </div>
      </article>
    </section>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="rounded-xl border border-border bg-background-secondary/60 p-3"><p className="text-[10px] font-extrabold uppercase tracking-[0.1em] text-foreground-muted">{label}</p><p className="mt-1 text-sm font-bold text-foreground">{value}</p><p className="mt-1 text-[10px] leading-4 text-foreground-muted capitalize">{detail}</p></div>;
}

function EmptyState({ icon: Icon, message }: { icon: typeof Network; message: string }) {
  return <div className="mt-5 flex min-h-24 items-center gap-3 rounded-xl border border-dashed border-border bg-background-secondary/35 p-4"><Icon size={18} className="shrink-0 text-foreground-muted" /><p className="text-xs leading-5 text-foreground-muted">{message}</p></div>;
}
