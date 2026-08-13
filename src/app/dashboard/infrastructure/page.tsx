"use client";

import {
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  CheckCircle2,
  FolderGit2,
  Loader2,
  MessageSquareText,
  Rocket,
  Send,
  Sparkles,
} from "lucide-react";
import { DecisionIntelligencePanel } from "@/components/dashboard/DecisionIntelligencePanel";
import { InfrastructurePlan as InfrastructurePlanView } from "@/components/dashboard/InfrastructurePlan";
import { ProjectSelector } from "@/components/dashboard/ProjectSelector";
import { ProjectTabs } from "@/components/dashboard/ProjectTabs";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  api,
  getErrorMessage,
  type DigitalTwinSimulation,
  type InfrastructurePlan,
  type InfrastructurePlanUpdate,
} from "@/lib/api";
import { useNotifications } from "@/lib/NotificationContext";

type PlanAction = "generate" | "update" | "approve" | "deploy" | null;

export default function InfrastructurePage() {
  return (
    <Suspense fallback={<InfrastructurePlanLoading />}>
      <InfrastructureWorkspace />
    </Suspense>
  );
}

function InfrastructureWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const {
    projects,
    isLoading: projectsLoading,
    addToast,
    refreshProjects,
    refreshStats,
  } = useNotifications();
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [plan, setPlan] = useState<InfrastructurePlan | null>(null);
  const [preflight, setPreflight] = useState<DigitalTwinSimulation | null>(null);
  const [loadingPlan, setLoadingPlan] = useState(false);
  const [planAction, setPlanAction] = useState<PlanAction>(null);
  const [preflightBusy, setPreflightBusy] = useState(false);
  const [planMissing, setPlanMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);
  const planContext = useRef<{ projectId: string; revision: number | null }>({
    projectId: "",
    revision: null,
  });

  useEffect(() => {
    planContext.current = {
      projectId: selectedProjectId,
      revision: plan?.revision ?? null,
    };
  }, [plan?.revision, selectedProjectId]);

  useEffect(() => {
    const requestedProject = searchParams.get("project");
    if (requestedProject && projects.some((project) => project.id === requestedProject)) {
      setSelectedProjectId(requestedProject);
      return;
    }
    if (!selectedProjectId && projects.length > 0) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, searchParams, selectedProjectId]);

  const loadPlan = useCallback(async (projectId: string) => {
    if (!projectId) return;
    const currentRequest = ++requestId.current;
    setLoadingPlan(true);
    setError(null);
    setPlan(null);
    setPreflight(null);
    setPlanMissing(false);

    try {
      const nextPlan = await api.getInfrastructurePlan(projectId);
      if (currentRequest !== requestId.current) return;
      setPlan(nextPlan);

      try {
        const latestPreflight = await api.getLatestDigitalTwin(projectId);
        if (currentRequest === requestId.current) {
          setPreflight(latestPreflight);
        }
      } catch {
        // A plan can legitimately have no preflight result for its current revision.
      }
    } catch (err) {
      if (currentRequest !== requestId.current) return;
      if (err instanceof Error && err.message.includes("No infrastructure plan")) {
        setPlanMissing(true);
      } else {
        setError(getErrorMessage(err, "We couldn't load this infrastructure plan."));
      }
    } finally {
      if (currentRequest === requestId.current) {
        setLoadingPlan(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadPlan(selectedProjectId);
  }, [loadPlan, selectedProjectId]);

  const generatePlan = async () => {
    if (!selectedProjectId) return false;
    setPlanAction("generate");
    setError(null);
    try {
      const nextPlan = await api.generateInfrastructurePlan(selectedProjectId);
      setPlan(nextPlan);
      setPlanMissing(false);
      setPreflight(null);
      addToast("A new plan revision was generated from the latest saved analysis.", "success");
      return true;
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't generate an infrastructure plan."));
      return false;
    } finally {
      setPlanAction(null);
    }
  };

  const updatePlan = async (update: InfrastructurePlanUpdate) => {
    if (!selectedProjectId) return false;
    setPlanAction("update");
    setError(null);
    try {
      const nextPlan = await api.updateInfrastructurePlan(selectedProjectId, update);
      setPlan(nextPlan);
      setPreflight(null);
      addToast("Plan updated. The new revision requires review and approval.", "success");
      return true;
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't update that plan setting."));
      return false;
    } finally {
      setPlanAction(null);
    }
  };

  const approvePlan = async (note?: string) => {
    if (!selectedProjectId) return false;
    setPlanAction("approve");
    setError(null);
    try {
      const nextPlan = await api.approveInfrastructurePlan(selectedProjectId, note);
      setPlan(nextPlan);
      try {
        setPreflight(await api.getLatestDigitalTwin(selectedProjectId));
      } catch {
        setPreflight(null);
      }
      addToast(
        "Plan approved. Deployment prerequisites and runtime validation still apply.",
        "success",
      );
      return true;
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't approve this plan."));
      return false;
    } finally {
      setPlanAction(null);
    }
  };

  const runPreflight = async () => {
    if (!selectedProjectId) return;
    const checkedProjectId = selectedProjectId;
    const checkedRevision = plan?.revision ?? null;
    setPreflightBusy(true);
    setError(null);
    try {
      const result = await api.simulateDigitalTwin(selectedProjectId);
      if (
        planContext.current.projectId !== checkedProjectId ||
        planContext.current.revision !== checkedRevision
      ) {
        addToast(
          "The plan changed while checks were running. Run them again for the current revision.",
          "warning",
        );
        return;
      }
      setPreflight(result);
      addToast(
        result.status === "blocked"
          ? "Policy checks found blockers. No Azure resources were changed."
          : "Policy checks completed. No Azure resources were changed.",
        result.status === "blocked" ? "warning" : "success",
      );
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't run the policy checks."));
    } finally {
      setPreflightBusy(false);
    }
  };

  const startDeployment = async () => {
    const project = projects.find((item) => item.id === selectedProjectId);
    if (!project) return;
    setPlanAction("deploy");
    setError(null);
    try {
      const result = await api.startDeployment({
        project_id: project.id,
        branch: project.branch,
        environment: "production",
      });
      await Promise.all([refreshProjects(), refreshStats()]);
      addToast("Deployment workflow started.", "success");
      router.push(
        `/dashboard/deployments?id=${result.deployment_id}&repo=${encodeURIComponent(project.full_name)}`,
      );
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't start this deployment."));
    } finally {
      setPlanAction(null);
    }
  };

  const selectProject = (projectId: string) => {
    setPlan(null);
    setPreflight(null);
    setPlanMissing(false);
    setLoadingPlan(true);
    setSelectedProjectId(projectId);
    const nextSearchParams = new URLSearchParams(searchParams.toString());
    nextSearchParams.set("project", projectId);
    router.replace(`/dashboard/architect?${nextSearchParams.toString()}`, { scroll: false });
  };

  if (projectsLoading) {
    return <InfrastructurePlanLoading />;
  }

  if (projects.length === 0) {
    return (
      <div className="mx-auto max-w-7xl">
        <PageHeader
          eyebrow="AI Architect"
          title="Review an Azure deployment plan"
          description="Start from recorded repository evidence, then review and approve a saved deployment proposal."
        />
        <div className="mx-auto flex max-w-xl flex-col items-center rounded-2xl border border-dashed border-border bg-card px-6 py-14 text-center shadow-sm">
          <span className="grid h-14 w-14 place-items-center rounded-2xl bg-primary-subtle text-primary">
            <FolderGit2 size={26} aria-hidden="true" />
          </span>
          <h2 className="mt-5 text-xl font-semibold tracking-tight text-foreground">Start with a repository</h2>
          <p className="mt-2 text-sm leading-6 text-foreground-muted">
            Connect GitHub or upload a ZIP so ZeroOps can record source evidence before proposing an
            infrastructure plan.
          </p>
          <Link href="/dashboard/repositories" className="ops-primary mt-6 min-h-11 px-5">
            Connect application <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
      </div>
    );
  }

  const busy = planAction !== null;

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader
        eyebrow="AI Architect"
        title="Architecture"
        description="Review the source-backed Azure plan, make supported changes, and approve one revision before deployment."
        actions={
          <fieldset
            disabled={busy || preflightBusy}
            className="w-full disabled:cursor-not-allowed disabled:opacity-60 sm:w-80"
          >
            <ProjectSelector
              projects={projects}
              value={selectedProjectId}
              onChange={selectProject}
              label="Application"
              className="w-full"
            />
          </fieldset>
        }
      />

      {selectedProjectId && <ProjectTabs projectId={selectedProjectId} />}

      {error && (
        <div
          role="alert"
          className="flex flex-col gap-3 rounded-xl border border-danger/25 bg-danger/10 px-4 py-3 text-sm text-foreground sm:flex-row sm:items-center sm:justify-between"
        >
          <p>{error}</p>
          <button
            type="button"
            disabled={loadingPlan || busy || preflightBusy}
            onClick={() => void loadPlan(selectedProjectId)}
            className="min-h-11 shrink-0 self-start px-2 text-sm font-semibold text-danger disabled:cursor-not-allowed disabled:opacity-60 sm:self-auto"
          >
            Reload plan
          </button>
        </div>
      )}

      {loadingPlan ? (
        <InfrastructurePlanLoading label="Loading saved plan…" />
      ) : plan ? (
        <>
          <InfrastructurePlanView
            plan={plan}
            onUpdate={updatePlan}
            onApprove={approvePlan}
            onRegenerate={generatePlan}
            busy={busy || preflightBusy}
          />

          <div className="grid gap-5 lg:grid-cols-2">
            <ArchitectChatPanel
              projectId={selectedProjectId}
              onPlanUpdated={(nextPlan) => {
                setPlan(nextPlan);
                setPreflight(null);
                addToast(
                  "The assistant created a new draft revision. Review it before approval.",
                  "success",
                );
              }}
            />
            <div className="min-w-0">
              <DecisionIntelligencePanel
                preflight={preflight}
                loading={preflightBusy}
                onRunPreflight={runPreflight}
              />
            </div>
          </div>

          {plan.status === "approved" && (
            <div className="flex flex-col gap-4 rounded-2xl border border-success/25 bg-success/10 p-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <CheckCircle2 size={16} className="text-success" aria-hidden="true" />
                  Revision {plan.revision} is approved
                </p>
                <p className="mt-1 text-xs leading-5 text-foreground-muted">
                  Starting deployment reruns prerequisites. Provisioning and the runtime health
                  check can still fail and will be recorded in deployment logs.
                </p>
              </div>
              <button
                type="button"
                disabled={busy || preflightBusy}
                onClick={() => void startDeployment()}
                className="ops-primary min-h-11 shrink-0 px-5 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {planAction === "deploy" ? (
                  <Loader2 size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                ) : (
                  <Rocket size={16} aria-hidden="true" />
                )}
                {planAction === "deploy" ? "Starting deployment" : "Start deployment"}
              </button>
            </div>
          )}
        </>
      ) : planMissing ? (
        <div className="mx-auto max-w-2xl rounded-3xl border border-border bg-card p-8 text-center shadow-sm">
          <Sparkles size={30} className="mx-auto text-primary" aria-hidden="true" />
          <h2 className="mt-4 text-xl font-bold text-foreground">
            Generate a plan from saved analysis
          </h2>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-foreground-muted">
            The proposal uses recorded framework, runtime, dependency, and configuration-key
            evidence. It does not infer live Azure state, pricing, or runtime readiness.
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() => void generatePlan()}
            className="ops-primary mt-6 min-h-11 px-5 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {planAction === "generate" ? (
              <Loader2 size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
            ) : (
              <Sparkles size={16} aria-hidden="true" />
            )}
            {planAction === "generate" ? "Generating plan" : "Generate plan"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

type ChatMessage = {
  id: string;
  sender: "user" | "architect" | "status";
  text: string;
};

const initialChatMessage: ChatMessage = {
  id: "architect-introduction",
  sender: "architect",
  text: "Ask why a service was proposed, or use an explicit command to create a new draft revision. Questions never change the plan.",
};

function ArchitectChatPanel({
  projectId,
  onPlanUpdated,
}: {
  projectId: string;
  onPlanUpdated: (plan: InfrastructurePlan) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([initialChatMessage]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const messageCounter = useRef(0);
  const activeProjectId = useRef(projectId);

  useEffect(() => {
    activeProjectId.current = projectId;
    setMessages([initialChatMessage]);
    setInput("");
    setBusy(false);
    messageCounter.current = 0;
  }, [projectId]);

  const nextMessageId = () => {
    messageCounter.current += 1;
    return `${projectId}-architect-message-${messageCounter.current}`;
  };

  const sendMessage = async (event: FormEvent) => {
    event.preventDefault();
    if (!input.trim() || busy) return;

    const userMessage = input.trim();
    setInput("");
    setMessages((current) => [
      ...current,
      { id: nextMessageId(), sender: "user", text: userMessage },
    ]);
    setBusy(true);

    try {
      const response = await api.architectChat(userMessage, projectId);
      if (activeProjectId.current !== projectId) return;
      setMessages((current) => [
        ...current,
        { id: nextMessageId(), sender: "architect", text: response.reply },
      ]);
      if (response.plan_updated && response.plan) {
        onPlanUpdated(response.plan);
      }
    } catch (err) {
      if (activeProjectId.current !== projectId) return;
      setMessages((current) => [
        ...current,
        {
          id: nextMessageId(),
          sender: "status",
          text: `${getErrorMessage(err, "The architect request failed.")} Review the plan and try again.`,
        },
      ]);
    } finally {
      if (activeProjectId.current === projectId) {
        setBusy(false);
      }
    }
  };

  return (
    <section
      aria-labelledby="architect-chat-heading"
      className="ops-card flex h-[28rem] min-h-[24rem] flex-col rounded-2xl border border-border bg-card p-4 sm:p-5"
    >
      <div className="mb-3 border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <MessageSquareText size={17} className="text-primary" aria-hidden="true" />
          <h2 id="architect-chat-heading" className="text-sm font-semibold text-foreground">
            Plan assistant
          </h2>
        </div>
        <p id="architect-chat-note" className="mt-1.5 text-[11px] leading-4 text-foreground-muted">
          Answers use the saved plan. Explicit commands can create a draft revision, but never
          approve or deploy it. Chat history is not persisted.
        </p>
      </div>

      <div
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        aria-label="Plan assistant conversation"
        className="flex-1 space-y-3 overflow-y-auto pr-1 text-xs"
      >
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.sender === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[90%] rounded-2xl p-3 leading-5 ${
                message.sender === "user"
                  ? "bg-primary text-primary-foreground"
                  : message.sender === "status"
                    ? "border border-danger/25 bg-danger/10 text-foreground"
                    : "bg-background-secondary/60 text-foreground-muted"
              }`}
            >
              {message.text}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex justify-start">
            <div className="flex max-w-[90%] items-center gap-1.5 rounded-2xl bg-background-secondary/60 p-3 text-foreground-muted">
              <Loader2 className="animate-spin text-primary motion-reduce:animate-none" size={12} aria-hidden="true" />
              Reviewing the saved plan…
            </div>
          </div>
        )}
      </div>

      <form onSubmit={sendMessage} className="mt-3 flex gap-2">
        <label className="min-w-0 flex-1">
          <span className="sr-only">Ask the plan assistant</span>
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask about this plan…"
            disabled={busy}
            aria-describedby="architect-chat-note"
            className="min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none placeholder:text-foreground-muted focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60"
          />
        </label>
        <button
          type="submit"
          disabled={busy || !input.trim()}
          aria-label="Send message"
          className="ops-primary min-h-11 min-w-11 px-3 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Send size={15} aria-hidden="true" />
          <span className="hidden sm:inline">Send</span>
        </button>
      </form>
    </section>
  );
}

function InfrastructurePlanLoading({ label = "Preparing architecture workspace…" }: { label?: string }) {
  return (
    <div
      role="status"
      className="flex min-h-[50vh] items-center justify-center gap-3 text-sm font-semibold text-foreground-muted"
    >
      <Loader2 className="animate-spin text-primary motion-reduce:animate-none" size={18} aria-hidden="true" />
      {label}
    </div>
  );
}
