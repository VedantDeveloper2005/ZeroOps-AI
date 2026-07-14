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

export function DecisionIntelligencePanel({ graph, simulation, accuracy, loading = false, onRunSimulation }: Props) {
  const labels = new Map(graph?.graph.nodes.map((node) => [node.id, node.label]) || []);
  const visibleEdges = (graph?.graph.edges || []).slice(0, 5);
  const attentionChecks = simulation?.checks.filter((check) => check.status !== "passed") || [];
  const passedChecks = simulation?.checks.filter((check) => check.status === "passed") || [];

  return (
    <section aria-labelledby="decision-intelligence-heading" className="mx-auto max-w-7xl space-y-5">
      <div className="flex flex-col gap-4 border-y border-border py-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-semibold text-primary">Deployment confidence</p>
          <h2 id="decision-intelligence-heading" className="mt-1 text-xl font-semibold tracking-tight text-foreground">Preflight and decision record</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-foreground-muted">Run a read-only check before deployment. It reviews the selected plan, available target, and recorded application evidence without changing Azure.</p>
        </div>
        <button type="button" disabled={loading} onClick={() => void onRunSimulation()} className="ops-primary shrink-0 px-4 text-sm disabled:cursor-not-allowed disabled:opacity-60">
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />} {loading ? "Running preflight" : "Run preflight"}
        </button>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
        <article className="ops-card rounded-2xl p-5 sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <div><div className="flex items-center gap-2"><Activity size={18} className="text-primary" /><h3 className="text-base font-semibold text-foreground">Digital twin</h3></div><p className="mt-1.5 text-xs leading-5 text-foreground-muted">A non-mutating simulation of this exact architecture revision.</p></div>
            {simulation && <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide ${stateStyle[simulation.status]}`}>{simulation.status.replaceAll("_", " ")}</span>}
          </div>

          {simulation ? <>
            <div className="mt-5 flex flex-col gap-3 rounded-xl border border-border bg-background-secondary/45 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div><p className="text-xs font-medium text-foreground-muted">Risk score</p><p className="mt-1 text-2xl font-semibold tracking-tight text-foreground">{simulation.risk_score}<span className="text-sm font-medium text-foreground-muted">/100</span></p></div>
              <div className="border-l-0 border-border pl-0 text-left sm:border-l sm:pl-4 sm:text-right"><p className="text-xs font-medium text-foreground-muted">Target</p><p className="mt-1 text-sm font-semibold text-foreground">{simulation.snapshot.target_ready ? "Ready" : "Needs setup"}</p><p className="mt-0.5 text-xs text-foreground-muted">{simulation.snapshot.application_service || "No application service"}</p></div>
            </div>
            <p className="mt-4 text-xs leading-5 text-foreground-muted">{simulation.summary}</p>

            {attentionChecks.length > 0 && <div className="mt-5 space-y-2.5"><p className="text-xs font-semibold text-foreground">Needs your attention</p>{attentionChecks.map((check) => <CheckRow key={check.id} check={check} />)}</div>}
            {passedChecks.length > 0 && <details className="mt-4 rounded-xl border border-border px-3 py-2.5"><summary className="cursor-pointer text-xs font-medium text-foreground">{passedChecks.length} check{passedChecks.length === 1 ? "" : "s"} passed</summary><div className="mt-3 space-y-2">{passedChecks.map((check) => <CheckRow key={check.id} check={check} compact />)}</div></details>}
          </> : <EmptyState icon={Target} message="No preflight has been recorded yet. Run it to check the plan before any infrastructure work starts." />}
        </article>

        <div className="space-y-5">
          <article className="ops-card rounded-2xl p-5">
            <div className="flex items-center gap-2"><Network size={18} className="text-primary" /><h3 className="text-base font-semibold text-foreground">Evidence graph</h3></div>
            {graph ? <>
              <p className="mt-2 text-xs leading-5 text-foreground-muted">{graph.graph.nodes.length} evidence nodes and {graph.graph.edges.length} relationships inform plan v{graph.plan_revision ?? "—"}. Configuration values are never included.</p>
              <details className="mt-4 rounded-xl border border-border px-3 py-2.5"><summary className="cursor-pointer text-xs font-medium text-foreground">View key relationships</summary><div className="mt-3 space-y-2.5">{visibleEdges.map((edge, index) => <div key={`${edge.source}-${edge.target}-${index}`} className="flex items-start gap-2 text-xs leading-4"><GitBranch size={14} className="mt-0.5 shrink-0 text-primary" /><p className="min-w-0 text-foreground-muted"><span className="font-medium text-foreground">{labels.get(edge.source) || "Source"}</span> {edge.relation.replaceAll("_", " ")} <span className="font-medium text-foreground">{labels.get(edge.target) || "Target"}</span></p></div>)}</div></details>
            </> : <EmptyState icon={Network} message="The evidence graph is created when an architecture plan is generated." />}
          </article>

          <article className="ops-card rounded-2xl p-5">
            <div className="flex items-center gap-2"><BrainCircuit size={18} className="text-primary" /><h3 className="text-base font-semibold text-foreground">Decision outcomes</h3></div>
            {accuracy?.available ? <><p className="mt-4 text-2xl font-semibold tracking-tight text-foreground">{accuracy.outcome_accuracy_percent}%</p><p className="mt-1 text-xs leading-5 text-foreground-muted">{accuracy.successful_deployments} successful of {accuracy.evaluated_deployments} health-validated deployments.</p></> : <p className="mt-4 text-sm font-medium text-foreground">No evaluated deployments yet</p>}
            <p className="mt-2 text-xs leading-5 text-foreground-muted">{accuracy?.methodology || "Accuracy appears only after a real deployment completes or fails."}</p>
          </article>
        </div>
      </div>

      <details className="rounded-xl border border-border bg-card px-4 py-3.5">
        <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold text-foreground"><ShieldCheck size={17} className="text-primary" /> Safeguards before execution</summary>
        <div className="mt-3 grid gap-3 border-t border-border pt-3 text-xs leading-5 text-foreground-muted md:grid-cols-3">
          <p><span className="font-semibold text-foreground">Evidence first.</span> Recommendations use recorded repository facts and visible unknowns; generated language cannot run an infrastructure change directly.</p>
          <p><span className="font-semibold text-foreground">You stay in control.</span> A plan change invalidates approval. Deployment requires approval, a connected target, internal validation, and runtime health checks.</p>
          <p><span className="font-semibold text-foreground">Failures are contained.</span> Blocking checks stop execution before provisioning. Failed deployments are recorded and analyzed without autonomous remediation.</p>
        </div>
      </details>
    </section>
  );
}

function CheckRow({ check, compact = false }: { check: DigitalTwinSimulation["checks"][number]; compact?: boolean }) {
  return <div className={`flex gap-2.5 rounded-xl border border-border px-3 py-2.5 ${compact ? "bg-background-secondary/35" : "bg-card"}`}>
    {check.status === "passed" ? <CheckCircle2 size={16} className={`mt-0.5 shrink-0 ${checkStyle.passed}`} /> : check.status === "warning" ? <CircleAlert size={16} className={`mt-0.5 shrink-0 ${checkStyle.warning}`} /> : <XCircle size={16} className={`mt-0.5 shrink-0 ${checkStyle.blocked}`} />}
    <div className="min-w-0"><p className="text-xs font-semibold text-foreground">{check.label}{check.risk_weight > 0 && <span className="ml-2 font-medium text-foreground-muted">+{check.risk_weight} risk</span>}</p><p className="mt-0.5 text-xs leading-5 text-foreground-muted">{check.detail}</p></div>
  </div>;
}

function EmptyState({ icon: Icon, message }: { icon: typeof Network; message: string }) {
  return <div className="mt-5 flex min-h-24 items-center gap-3 rounded-xl border border-dashed border-border bg-background-secondary/35 p-4"><Icon size={18} className="shrink-0 text-foreground-muted" /><p className="text-xs leading-5 text-foreground-muted">{message}</p></div>;
}
