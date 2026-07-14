"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, FolderGit2, Loader2, Rocket, Sparkles } from "lucide-react";
import { DecisionIntelligencePanel } from "@/components/dashboard/DecisionIntelligencePanel";
import { InfrastructurePlan as InfrastructurePlanView } from "@/components/dashboard/InfrastructurePlan";
import { api, getErrorMessage, type DecisionAccuracy, type DigitalTwinSimulation, type InfrastructurePlan, type InfrastructurePlanUpdate, type KnowledgeGraph } from "@/lib/api";
import { useNotifications } from "@/lib/NotificationContext";

export default function InfrastructurePage() {
  return <Suspense fallback={<InfrastructurePlanLoading />}><InfrastructureWorkspace /></Suspense>;
}

function InfrastructureWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { projects, isLoading: projectsLoading, addToast, refreshProjects, refreshStats } = useNotifications();
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [plan, setPlan] = useState<InfrastructurePlan | null>(null);
  const [loadingPlan, setLoadingPlan] = useState(false);
  const [busy, setBusy] = useState(false);
  const [intelligenceBusy, setIntelligenceBusy] = useState(false);
  const [planMissing, setPlanMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [graph, setGraph] = useState<KnowledgeGraph | null>(null);
  const [simulation, setSimulation] = useState<DigitalTwinSimulation | null>(null);
  const [accuracy, setAccuracy] = useState<DecisionAccuracy | null>(null);

  useEffect(() => {
    const requestedProject = searchParams.get("project");
    if (requestedProject && projects.some((project) => project.id === requestedProject)) {
      setSelectedProjectId(requestedProject);
      return;
    }
    if (!selectedProjectId && projects.length > 0) setSelectedProjectId(projects[0].id);
  }, [projects, searchParams, selectedProjectId]);

  const loadIntelligence = useCallback(async (projectId: string) => {
    if (!projectId) return;
    const [graphResult, simulationResult, accuracyResult] = await Promise.allSettled([
      api.getKnowledgeGraph(projectId),
      api.getLatestDigitalTwin(projectId),
      api.getDecisionAccuracy(projectId),
    ]);
    setGraph(graphResult.status === "fulfilled" ? graphResult.value : null);
    setSimulation(simulationResult.status === "fulfilled" ? simulationResult.value : null);
    setAccuracy(accuracyResult.status === "fulfilled" ? accuracyResult.value : null);
  }, []);

  const loadPlan = useCallback(async (projectId: string) => {
    if (!projectId) return;
    setLoadingPlan(true);
    setError(null);
    setGraph(null);
    setSimulation(null);
    setAccuracy(null);
    try {
      const nextPlan = await api.getInfrastructurePlan(projectId);
      setPlan(nextPlan);
      setPlanMissing(false);
      await loadIntelligence(projectId);
    } catch (err) {
      setPlan(null);
      if (err instanceof Error && err.message.includes("No infrastructure plan")) {
        setPlanMissing(true);
      } else {
        setPlanMissing(false);
        setError(getErrorMessage(err, "We couldn't load this architecture plan."));
      }
    } finally {
      setLoadingPlan(false);
    }
  }, [loadIntelligence]);

  useEffect(() => {
    void loadPlan(selectedProjectId);
  }, [loadPlan, selectedProjectId]);

  const generatePlan = async () => {
    if (!selectedProjectId) return;
    setBusy(true);
    setError(null);
    try {
      const nextPlan = await api.generateInfrastructurePlan(selectedProjectId);
      setPlan(nextPlan);
      setPlanMissing(false);
      await loadIntelligence(selectedProjectId);
      addToast("Architecture plan generated from the latest repository analysis.", "success");
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't generate an infrastructure plan."));
    } finally {
      setBusy(false);
    }
  };

  const updatePlan = async (update: InfrastructurePlanUpdate) => {
    if (!selectedProjectId) return;
    setBusy(true);
    setError(null);
    try {
      const nextPlan = await api.updateInfrastructurePlan(selectedProjectId, update);
      setPlan(nextPlan);
      await loadIntelligence(selectedProjectId);
      addToast("Architecture plan updated. Review it again before deployment.", "success");
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't update that architecture setting."));
    } finally {
      setBusy(false);
    }
  };

  const approvePlan = async (note?: string) => {
    if (!selectedProjectId) return;
    setBusy(true);
    setError(null);
    try {
      const nextPlan = await api.approveInfrastructurePlan(selectedProjectId, note);
      setPlan(nextPlan);
      await loadIntelligence(selectedProjectId);
      addToast("Architecture plan approved. You can now start the deployment workflow.", "success");
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't approve this plan."));
    } finally {
      setBusy(false);
    }
  };

  const runSimulation = async () => {
    if (!selectedProjectId) return;
    setIntelligenceBusy(true);
    setError(null);
    try {
      const nextSimulation = await api.simulateDigitalTwin(selectedProjectId);
      setSimulation(nextSimulation);
      const [nextGraph, nextAccuracy] = await Promise.allSettled([
        api.getKnowledgeGraph(selectedProjectId),
        api.getDecisionAccuracy(selectedProjectId),
      ]);
      if (nextGraph.status === "fulfilled") setGraph(nextGraph.value);
      if (nextAccuracy.status === "fulfilled") setAccuracy(nextAccuracy.value);
      addToast(
        nextSimulation.status === "blocked"
          ? "Preflight found blocking checks. No infrastructure change was made."
          : "Digital-twin preflight completed.",
        nextSimulation.status === "blocked" ? "warning" : "success",
      );
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't run the digital-twin preflight."));
    } finally {
      setIntelligenceBusy(false);
    }
  };

  const startDeployment = async () => {
    const project = projects.find((item) => item.id === selectedProjectId);
    if (!project) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.startDeployment({ project_id: project.id, branch: project.branch, environment: "production" });
      await Promise.all([refreshProjects(), refreshStats()]);
      addToast("Deployment workflow started.", "success");
      router.push(`/dashboard/deployments?id=${result.deployment_id}&repo=${encodeURIComponent(project.full_name)}`);
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't start this deployment."));
    } finally {
      setBusy(false);
    }
  };

  if (projectsLoading) {
    return <div className="flex min-h-[50vh] items-center justify-center gap-3 text-sm font-semibold text-foreground-muted"><Loader2 className="animate-spin text-primary" size={18} /> Loading applications…</div>;
  }

  if (projects.length === 0) {
    return <div className="mx-auto flex max-w-xl flex-col items-center rounded-3xl border border-dashed border-border bg-card/60 px-6 py-16 text-center"><FolderGit2 size={38} className="text-primary" /><h1 className="mt-5 text-xl font-bold text-foreground">Start with a repository</h1><p className="mt-2 text-sm leading-6 text-foreground-muted">Connect GitHub or upload a ZIP so ZeroOps can analyze your application and propose an architecture from real source evidence.</p><button onClick={() => router.push("/dashboard/repositories")} className="ops-primary mt-6 px-5"><ArrowRight size={16} /> Connect application</button></div>;
  }

  return <div className="space-y-5">
    <div className="mx-auto flex max-w-7xl flex-col gap-3 rounded-2xl border border-border bg-card/70 p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
      <div><p className="text-[10px] font-extrabold uppercase tracking-[0.13em] text-primary">Architecture workspace</p><p className="mt-1 text-sm font-bold text-foreground">Choose the application you want ZeroOps to architect.</p></div>
      <select value={selectedProjectId} onChange={(event) => setSelectedProjectId(event.target.value)} className="min-h-11 max-w-full rounded-xl border border-border bg-background-secondary px-3 text-sm font-semibold text-foreground outline-none focus:border-primary sm:w-80">
        {projects.map((project) => <option key={project.id} value={project.id}>{project.full_name}</option>)}
      </select>
    </div>

    {error && <div role="alert" className="mx-auto max-w-7xl rounded-xl border border-danger/25 bg-danger/10 px-4 py-3 text-sm text-foreground">{error}</div>}

    {loadingPlan ? <div className="flex min-h-[45vh] items-center justify-center gap-3 text-sm font-semibold text-foreground-muted"><Loader2 className="animate-spin text-primary" size={18} /> Loading architecture decisions…</div> : plan ? <>
      <InfrastructurePlanView plan={plan} onUpdate={updatePlan} onApprove={approvePlan} onRegenerate={generatePlan} busy={busy} />
      <DecisionIntelligencePanel graph={graph} simulation={simulation} accuracy={accuracy} loading={busy || intelligenceBusy} onRunSimulation={runSimulation} />
      {plan.status === "approved" && <div className="mx-auto flex max-w-7xl flex-col gap-4 rounded-2xl border border-success/25 bg-success/10 p-5 sm:flex-row sm:items-center sm:justify-between"><div><p className="flex items-center gap-2 text-sm font-bold text-foreground"><Sparkles size={16} className="text-success" /> Architecture approved</p><p className="mt-1 text-xs leading-5 text-foreground-muted">ZeroOps will prepare the internal infrastructure workflow, deploy the application, and validate the resulting service.</p></div><button disabled={busy} onClick={() => void startDeployment()} className="ops-primary shrink-0 px-5 disabled:opacity-60"><Rocket size={16} /> Start deployment</button></div>}
    </> : planMissing ? <div className="mx-auto max-w-2xl rounded-3xl border border-border bg-card p-8 text-center shadow-sm"><Sparkles size={30} className="mx-auto text-primary" /><h1 className="mt-4 text-xl font-bold text-foreground">Create an AI infrastructure plan</h1><p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-foreground-muted">We&apos;ll use the application&apos;s recorded analysis to recommend an Azure architecture. Implementation details and credentials stay protected in the deployment engine.</p><button disabled={busy} onClick={() => void generatePlan()} className="ops-primary mt-6 px-5 disabled:opacity-60"><Sparkles size={16} /> Generate plan</button></div> : null}
  </div>;
}

function InfrastructurePlanLoading() {
  return <div className="flex min-h-[50vh] items-center justify-center gap-3 text-sm font-semibold text-foreground-muted"><Loader2 className="animate-spin text-primary" size={18} /> Preparing architecture workspace…</div>;
}
