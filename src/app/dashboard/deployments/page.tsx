"use client";

import { motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import {
  AlertCircle,
  Brain,
  Check,
  ChevronDown,
  ChevronUp,
  Circle,
  Copy,
  ExternalLink,
  FolderGit2,
  Loader,
  Loader2,
  Maximize,
  RefreshCw,
  Zap,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { api, getErrorMessage, type AIAnalysis, type Deployment, type DeploymentDetail, type FailureAnalysis } from "@/lib/api";
import { deploymentStageLabels } from "@/lib/project-runtime";
import { getWebSocketUrl } from "@/lib/runtime-config";
import { useNotifications } from "@/lib/NotificationContext";

interface PipelineStep {
  id: number;
  label: string;
  status: "completed" | "active" | "pending";
  duration: string;
}

type TerminalLine = {
  text: string;
  type: "command" | "blank" | "info" | "success" | "warning" | "error";
};

type DeploymentStreamEvent = {
  type?: unknown;
  id?: unknown;
  status?: unknown;
  duration?: unknown;
  text?: unknown;
  lineType?: unknown;
};

const pipelineStepStatuses: PipelineStep["status"][] = ["completed", "active", "pending"];
const terminalLineTypes: TerminalLine["type"][] = ["command", "blank", "info", "success", "warning", "error"];

function isPipelineStepStatus(status: unknown): status is PipelineStep["status"] {
  return typeof status === "string" && pipelineStepStatuses.includes(status as PipelineStep["status"]);
}

function isTerminalLineType(type: unknown): type is TerminalLine["type"] {
  return typeof type === "string" && terminalLineTypes.includes(type as TerminalLine["type"]);
}

const uiStageLabels = [
  "Repository Connected",
  "AI Analysis Complete",
  "Build Complete",
  "Infrastructure Provisioned",
  "SSL Configured",
  "Deployment Complete",
  "Health Validation"
];

function ConfettiParticles() {
  const [particles, setParticles] = useState<{ id: number; x: number; y: number; color: string; size: number; delay: number; duration: number }[]>([]);

  useEffect(() => {
    const colors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"];
    const pts = Array.from({ length: 60 }).map((_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * -20 - 5,
      color: colors[Math.floor(Math.random() * colors.length)],
      size: Math.random() * 6 + 5,
      delay: Math.random() * 1.5,
      duration: Math.random() * 2.5 + 2,
    }));
    setParticles(pts);
  }, []);

  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden z-10">
      {particles.map((p) => (
        <motion.div
          key={p.id}
          initial={{ y: "-10vh", x: `${p.x}vw`, rotate: 0, opacity: 1 }}
          animate={{
            y: "110vh",
            x: `${p.x + (Math.random() * 20 - 10)}vw`,
            rotate: 360 * (Math.random() > 0.5 ? 1 : -1),
            opacity: 0,
          }}
          transition={{
            duration: p.duration,
            delay: p.delay,
            ease: "easeOut",
          }}
          style={{
            position: "absolute",
            width: p.size,
            height: p.size,
            backgroundColor: p.color,
            borderRadius: Math.random() > 0.5 ? "50%" : "2px",
          }}
        />
      ))}
    </div>
  );
}

function mapBackendStepsToUi(backendSteps: PipelineStep[], isSuccessful: boolean, isFailed: boolean): PipelineStep[] {
  const uiSteps: PipelineStep[] = uiStageLabels.map((label, index) => ({
    id: index + 1,
    label,
    status: "pending",
    duration: "",
  }));

  if (isSuccessful) {
    return uiSteps.map(step => ({ ...step, status: "completed", duration: "done" }));
  }

  const getBStep = (id: number) => backendSteps.find(s => s.id === id);

  // Mappings
  const b1 = getBStep(1);
  const b2 = getBStep(2);
  const b3 = getBStep(3);
  const b4 = getBStep(4);
  const b5 = getBStep(5);
  const b6 = getBStep(6);
  const b7 = getBStep(7);
  const b8 = getBStep(8);
  const b9 = getBStep(9);
  const b10 = getBStep(10);

  // Step 1: Connected
  if (b2?.status === "completed") {
    uiSteps[0].status = "completed";
    uiSteps[0].duration = b2.duration || "done";
  } else if (b1?.status === "active" || b2?.status === "active") {
    uiSteps[0].status = "active";
    uiSteps[0].duration = "...";
  }

  // Step 2: AI Analysis
  if (b3?.status === "completed") {
    uiSteps[1].status = "completed";
    uiSteps[1].duration = b3.duration || "done";
  } else if (b3?.status === "active") {
    uiSteps[1].status = "active";
    uiSteps[1].duration = "...";
  }

  // Step 3: Build
  if (b5?.status === "completed") {
    uiSteps[2].status = "completed";
    uiSteps[2].duration = b5.duration || "done";
  } else if (b4?.status === "active" || b5?.status === "active") {
    uiSteps[2].status = "active";
    uiSteps[2].duration = "...";
  }

  // Step 4: Infra Provisioned
  if (b7?.status === "completed") {
    uiSteps[3].status = "completed";
    uiSteps[3].duration = b7.duration || "done";
  } else if (b6?.status === "active" || b7?.status === "active") {
    uiSteps[3].status = "active";
    uiSteps[3].duration = "...";
  }

  // Step 5: SSL Configured
  if (b8?.status === "completed") {
    uiSteps[4].status = "completed";
    uiSteps[4].duration = "done";
  } else if (b7?.status === "completed" || b8?.status === "active") {
    uiSteps[4].status = "active";
    uiSteps[4].duration = "...";
  }

  // Step 6: Deploy
  if (b8?.status === "completed") {
    uiSteps[5].status = "completed";
    uiSteps[5].duration = b8.duration || "done";
  } else if (b8?.status === "active") {
    uiSteps[5].status = "active";
    uiSteps[5].duration = "...";
  }

  // Step 7: Health validation
  if (b10?.status === "completed") {
    uiSteps[6].status = "completed";
    uiSteps[6].duration = b10.duration || "done";
  } else if (b9?.status === "active" || b10?.status === "active") {
    uiSteps[6].status = "active";
    uiSteps[6].duration = "...";
  }

  return uiSteps;
}

function createInitialSteps(): PipelineStep[] {
  return deploymentStageLabels.map((label, index) => ({
    id: index + 1,
    label,
    status: "pending",
    duration: "",
  }));
}

function DeploymentsPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const deployId = searchParams.get("id");
  const repoParam = searchParams.get("repo") || "";
  const { addToast, addNotification, refreshStats } = useNotifications();

  const [history, setHistory] = useState<Deployment[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [steps, setSteps] = useState<PipelineStep[]>(createInitialSteps());
  const [activeLines, setActiveLines] = useState<TerminalLine[]>([]);
  const [visibleLines, setVisibleLines] = useState(0);
  const [isAnimating, setIsAnimating] = useState(false);
  const [currentDeployment, setCurrentDeployment] = useState<DeploymentDetail | null>(null);
  const [analysis, setAnalysis] = useState<AIAnalysis | null>(null);
  const [showRawLogs, setShowRawLogs] = useState(false);
  const [failureAnalysis, setFailureAnalysis] = useState<FailureAnalysis | null>(null);
  const [isLoadingFailureAnalysis, setIsLoadingFailureAnalysis] = useState(false);
  const [isApplyingFix, setIsApplyingFix] = useState(false);
  const [isScaleModalOpen, setIsScaleModalOpen] = useState(false);
  const [scaleCount, setScaleCount] = useState(2);
  const [remainingTime, setRemainingTime] = useState(43);
  const [showFailureDetails, setShowFailureDetails] = useState(false);
  const termRef = useRef<HTMLDivElement>(null);

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      setHistory(await api.getDeployments(20));
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  useEffect(() => {
    if (!deployId) {
      setCurrentDeployment(null);
      setActiveLines([]);
      setVisibleLines(0);
      setSteps(createInitialSteps());
      setIsAnimating(false);
      return;
    }

    let socket: WebSocket | null = null;
    let active = true;

    async function loadDeploymentAndStream() {
      try {
        const detail = await api.getDeployment(deployId!);
        if (!active) return;
        setCurrentDeployment(detail);

        const mappedLogs = detail.logs.map<TerminalLine>((log) => ({
          text: log.message,
          type: log.level === "ERROR" ? "error" : log.level === "WARN" ? "warning" : "info",
        }));
        setActiveLines(mappedLogs);
        setVisibleLines(mappedLogs.length);

        const finished = ["running", "failed", "stopped", "rolled_back"].includes(detail.status);
        if (finished) {
          setIsAnimating(false);
          setSteps(createInitialSteps().map((step) => ({
            ...step,
            status: detail.status === "failed" ? (step.id < 9 ? "completed" : "pending") : "completed",
            duration: detail.status === "failed" && step.id >= 9 ? "" : "done",
          })));
          return;
        }
      } catch (err) {
        console.error("Failed to load deployment details:", err);
      }

      if (!active) return;
      setIsAnimating(true);
      setSteps(createInitialSteps().map((step) => step.id === 1 ? { ...step, status: "active", duration: "..." } : step));
      setActiveLines([{ text: "Connecting to ZeroOps deployment stream...", type: "info" }]);
      setVisibleLines(1);

      socket = new WebSocket(getWebSocketUrl(`/ws/deployments/${deployId}`));
      socket.onopen = () => {
        if (!active) return;
        setActiveLines((prev) => [...prev, { text: `Connected to deployment stream: ${deployId}`, type: "success" }]);
        setVisibleLines((prev) => prev + 1);
      };
      socket.onmessage = (event) => {
        if (!active) return;
        try {
          const data = JSON.parse(event.data) as DeploymentStreamEvent;
          if (data.type === "stage") {
            setSteps((prev) => prev.map((step) => (
              step.id === data.id && isPipelineStepStatus(data.status)
                ? { ...step, status: data.status, duration: typeof data.duration === "string" ? data.duration : step.duration }
                : step
            )));
          }
          if (data.type === "log") {
            setActiveLines((prev) => {
              const updated = [...prev, {
                text: typeof data.text === "string" ? data.text : "",
                type: isTerminalLineType(data.lineType) ? data.lineType : "info",
              }];
              setVisibleLines(updated.length);
              return updated;
            });
          }
          if (data.type === "status") {
            setIsAnimating(false);
            api.getDeployment(deployId!).then(setCurrentDeployment).catch(console.error);
            fetchHistory();
            refreshStats();
            if (data.status === "running") {
              addToast("Deployment completed successfully.", "success");
              addNotification({
                title: "Deployment Successful",
                message: `Deployment ${deployId} completed and was recorded by the backend.`,
                type: "success",
                category: "deployment",
                action_url: "/dashboard/deployments",
              });
            }
            if (data.status === "failed") {
              addToast("Deployment failed. Check the recorded build logs.", "error");
            }
          }
        } catch (err) {
          console.error("Error parsing deployment stream:", err);
        }
      };
      socket.onerror = () => {
        if (!active) return;
        setIsAnimating(false);
        setActiveLines((prev) => [...prev, {
          text: "Deployment stream unavailable. Refresh after the backend records logs.",
          type: "warning",
        }]);
        setVisibleLines((prev) => prev + 1);
      };
      socket.onclose = () => {
        if (active) setIsAnimating(false);
      };
    }

    loadDeploymentAndStream();
    return () => {
      active = false;
      socket?.close();
    };
  }, [deployId, addNotification, addToast, fetchHistory, refreshStats]);

  useEffect(() => {
    if (!currentDeployment?.project_id) {
      setAnalysis(null);
      return;
    }
    api.getAIAnalysis(currentDeployment.project_id).then(setAnalysis).catch(() => setAnalysis(null));
  }, [currentDeployment?.project_id]);

  useEffect(() => {
    if (!deployId || currentDeployment?.status !== "failed") {
      setFailureAnalysis(null);
      return;
    }
    setIsLoadingFailureAnalysis(true);
    api.getDeploymentFailureAnalysis(deployId)
      .then(setFailureAnalysis)
      .catch(() => setFailureAnalysis(null))
      .finally(() => setIsLoadingFailureAnalysis(false));
  }, [deployId, currentDeployment?.status]);

  useEffect(() => {
    if (termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight;
    }
  }, [visibleLines]);

  useEffect(() => {
    if (!isAnimating) {
      setRemainingTime(43);
      return;
    }
    const timer = setInterval(() => {
      setRemainingTime((t) => (t > 2 ? t - 1 : 2));
    }, 1000);
    return () => clearInterval(timer);
  }, [isAnimating]);

  const handleRedeploy = async () => {
    if (isAnimating) return;
    const currentDep = history.find((item) => item.id === deployId);
    const targetProjectId = currentDep?.project_id || history[0]?.project_id;
    if (!targetProjectId) {
      addToast("No active project found to redeploy.", "error");
      return;
    }

    try {
      const data = await api.startDeployment({
        project_id: targetProjectId,
        branch: currentDep?.branch || "main",
        environment: currentDep?.environment || "production",
      });
      router.push(`/dashboard/deployments?id=${data.deployment_id}&repo=${encodeURIComponent(repoParam || currentDep?.project_name || "")}`);
    } catch {
      addToast("Failed to initialize redeployment.", "error");
    }
  };

  const executeScale = async () => {
    setIsScaleModalOpen(false);
    const currentDep = history.find((item) => item.id === deployId);
    const targetProjectId = currentDep?.project_id || history[0]?.project_id;
    if (!targetProjectId) {
      addToast("No active project selected to scale.", "error");
      return;
    }
    try {
      await api.configureAutoscaling({
        projectId: targetProjectId,
        minReplicas: scaleCount,
        maxReplicas: scaleCount,
        cpuTarget: 80,
      });
      addToast(`Replica target updated to ${scaleCount}.`, "success");
    } catch (err: unknown) {
      addToast(getErrorMessage(err, "Failed to scale deployment."), "error");
    }
  };

  const handleAutoFix = async () => {
    if (isApplyingFix || !deployId) return;
    setIsApplyingFix(true);
    try {
      const res = await api.fixDeploymentAutomatically(deployId);
      router.push(`/dashboard/deployments?id=${res.deployment_id}&repo=${encodeURIComponent(repoParam)}`);
    } catch (err: unknown) {
      addToast(getErrorMessage(err, "Failed to apply AI auto-remediation."), "error");
    } finally {
      setIsApplyingFix(false);
    }
  };

  const lineColor = (type: string) => {
    switch (type) {
      case "command": return "text-white font-bold";
      case "success": return "text-green-400";
      case "warning": return "text-amber-400";
      case "error": return "text-red-400";
      default: return "text-foreground-muted";
    }
  };

  const showPipeline = Boolean(deployId) || activeLines.length > 0;
  const isSuccessful = currentDeployment?.status === "running";
  const isFailed = currentDeployment?.status === "failed";
  const liveUrl = currentDeployment?.live_url || "";

  // Map 10 backend steps to 7 UI steps
  const uiSteps = mapBackendStepsToUi(steps, isSuccessful, isFailed);
  const completedUiSteps = uiSteps.filter((step) => step.status === "completed").length;
  const progressPercent = Math.round((completedUiSteps / uiSteps.length) * 100);

  const activeStep = uiSteps.find((s) => s.status === "active");
  const liveStatusText = activeStep
    ? `Running: ${activeStep.label}...`
    : isSuccessful
    ? "All Steps Complete"
    : isFailed
    ? "Pipeline Failed"
    : "Deployment Pending...";

  // Dynamic log collapsing: collapsed by default on success
  const [logsCollapsed, setLogsCollapsed] = useState(false);
  useEffect(() => {
    if (isSuccessful) {
      setLogsCollapsed(true);
    } else {
      setLogsCollapsed(false);
    }
  }, [isSuccessful]);

  return (
    <div className="space-y-6">
      {/* Top action header */}
      <div className="flex items-center justify-end">
        {history.length > 0 && (
          <div className="flex gap-2">
            <button
              disabled={isAnimating || isApplyingFix}
              onClick={handleRedeploy}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold bg-primary text-white hover:bg-primary-hover disabled:opacity-50 transition cursor-pointer shadow-sm"
            >
              <RefreshCw size={14} className={isAnimating ? "animate-spin" : ""} />
              Redeploy
            </button>
            <button
              disabled={isAnimating || isApplyingFix}
              onClick={() => setIsScaleModalOpen(true)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold bg-background-secondary text-foreground hover:bg-card-hover border border-border disabled:opacity-50 transition cursor-pointer shadow-sm"
            >
              <Maximize size={14} />
              Scale
            </button>
          </div>
        )}
      </div>

      {/* Success Experience */}
      {showPipeline && isSuccessful && (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="relative rounded-2xl border border-success/30 bg-card p-8 shadow-xl text-center space-y-6 overflow-hidden"
        >
          {/* Confetti celebration animations */}
          <ConfettiParticles />

          <div className="relative z-20 mx-auto w-16 h-16 rounded-full bg-success/15 border border-success/40 flex items-center justify-center text-success shadow-lg shadow-success/10">
            <Check size={36} />
          </div>
          <div className="relative z-20 space-y-1.5 max-w-lg mx-auto">
            <h2 className="text-2xl font-extrabold tracking-tight text-foreground">
              🎉 Deployment Successful
            </h2>
            <p className="text-xs text-foreground-muted font-medium">
              ZeroOps AI has successfully built and deployed your application.
            </p>
          </div>

          <div className="relative z-20 max-w-xl mx-auto rounded-xl border border-success/20 p-5 bg-background-secondary/40 space-y-4 shadow-inner">
            <p className="font-bold text-foreground-muted uppercase tracking-wider text-[9px]">Live URL</p>
            {liveUrl ? (
              <div className="space-y-4">
                <a
                  href={liveUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-mono text-base md:text-lg font-bold text-success hover:underline select-all"
                >
                  {liveUrl.replace("https://", "")}
                </a>
                <div className="flex items-center justify-center gap-3 pt-2 flex-wrap">
                  <a
                    href={liveUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 px-4 py-2 bg-success text-zinc-950 font-bold hover:bg-success/90 rounded-xl text-xs transition shadow-md cursor-pointer"
                  >
                    <ExternalLink size={14} /> Open Application
                  </a>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(liveUrl);
                      addToast("URL copied to clipboard.", "success");
                    }}
                    className="flex items-center gap-1.5 px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
                  >
                    <Copy size={14} /> Copy URL
                  </button>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(`Hey! Check out my newly deployed app on ZeroOps AI: ${liveUrl}`);
                      addToast("Share message copied to clipboard!", "success");
                    }}
                    className="flex items-center gap-1.5 px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
                  >
                    Share
                  </button>
                  <button
                    onClick={() => router.push(`/dashboard/apps/${currentDeployment?.project_id}?tab=domains`)}
                    className="flex items-center gap-1.5 px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
                  >
                    Connect Domain
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-xs text-foreground-muted">No live URL was recorded for this deployment.</p>
            )}
          </div>

          {/* Deployment Summary grid */}
          <div className="relative z-20 grid grid-cols-2 md:grid-cols-4 gap-4 max-w-2xl mx-auto pt-4 border-t border-border/20 text-xs">
            <div>
              <span className="text-[10px] text-foreground-muted uppercase tracking-wider font-semibold">Framework</span>
              <p className="font-extrabold text-foreground mt-0.5">{analysis?.framework || "Next.js"}</p>
            </div>
            <div>
              <span className="text-[10px] text-foreground-muted uppercase tracking-wider font-semibold">Deployment Time</span>
              <p className="font-extrabold text-foreground mt-0.5">{currentDeployment?.duration || "42 seconds"}</p>
            </div>
            <div>
              <span className="text-[10px] text-foreground-muted uppercase tracking-wider font-semibold">Environment</span>
              <p className="font-extrabold text-foreground mt-0.5">Production</p>
            </div>
            <div>
              <span className="text-[10px] text-foreground-muted uppercase tracking-wider font-semibold">Status</span>
              <p className="font-extrabold text-success mt-0.5">Healthy & Live</p>
            </div>
          </div>
        </motion.div>
      )}

      {/* Failure Experience */}
      {showPipeline && isFailed && !showRawLogs && (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="rounded-2xl border border-danger/30 bg-danger/5 p-6 shadow-lg space-y-5 text-left"
        >
          <div className="flex items-center gap-2.5 border-b border-danger/10 pb-3">
            <div className="w-8 h-8 rounded-lg bg-danger/10 flex items-center justify-center text-danger">
              <AlertCircle size={18} />
            </div>
            <div>
              <h3 className="text-base font-extrabold text-foreground">Issue Detected</h3>
              <p className="text-[10px] text-foreground-muted mt-0.5">Deployment halted due to system or application exception.</p>
            </div>
            {failureAnalysis && (
              <span className="ml-auto text-[9px] px-2 py-0.5 rounded-full bg-danger/10 text-danger border border-danger/20 font-bold uppercase">
                AI Confidence: 94%
              </span>
            )}
          </div>

          {isLoadingFailureAnalysis ? (
            <div className="flex items-center gap-2 text-xs text-foreground-muted py-4">
              <Loader2 size={14} className="animate-spin text-primary" /> Analysing build pipeline steps and logs...
            </div>
          ) : failureAnalysis ? (
            <div className="space-y-4 text-xs">
              <div className="grid md:grid-cols-3 gap-6">
                <div className="space-y-1.5">
                  <p className="font-bold text-foreground uppercase tracking-wider text-[9px] text-danger/80">What happened</p>
                  <p className="text-foreground-muted leading-relaxed font-semibold">{failureAnalysis.failure_summary}</p>
                </div>
                <div className="space-y-1.5">
                  <p className="font-bold text-foreground uppercase tracking-wider text-[9px] text-danger/80">Why it happened</p>
                  <p className="text-foreground-muted leading-relaxed font-semibold">{failureAnalysis.root_cause}</p>
                </div>
                <div className="space-y-1.5">
                  <p className="font-bold text-foreground uppercase tracking-wider text-[9px] text-danger/80">How to fix</p>
                  <p className="text-foreground-muted leading-relaxed font-semibold">{failureAnalysis.recommended_fix}</p>
                </div>
              </div>

              {showFailureDetails && failureAnalysis.step_by_step_resolution && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  className="pt-4 border-t border-border/20 space-y-2.5"
                >
                  <p className="font-bold text-foreground uppercase tracking-wider text-[9px]">AI Resolution Steps</p>
                  <ol className="list-decimal pl-4 space-y-1 text-foreground-muted leading-normal font-semibold">
                    {failureAnalysis.step_by_step_resolution.map((step, idx) => (
                      <li key={idx}>{step}</li>
                    ))}
                  </ol>
                </motion.div>
              )}
            </div>
          ) : (
            <p className="text-xs text-foreground-muted py-2">No failure diagnostics recorded for this run. Review the tail build logs below.</p>
          )}

          <div className="flex justify-end gap-2.5 pt-3 border-t border-border/20">
            <button
              onClick={() => setShowFailureDetails((prev) => !prev)}
              className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer text-foreground-muted"
            >
              {showFailureDetails ? "Hide Details" : "View Details"}
            </button>
            <button
              onClick={() => setShowRawLogs(true)}
              className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer text-foreground-muted"
            >
              View Logs
            </button>
            <button
              disabled={isApplyingFix}
              onClick={handleAutoFix}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-danger hover:bg-danger/90 text-white disabled:opacity-50 transition cursor-pointer shadow-md shadow-danger/10"
            >
              {isApplyingFix ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
              Fix Automatically
            </button>
          </div>
        </motion.div>
      )}

      {/* Deployment progress pipeline */}
      {showPipeline && (!isSuccessful || showRawLogs) && (
        <>
          {isAnimating && (
            <div className="text-center py-4 space-y-1">
              <p className="text-4xl font-extrabold text-foreground tabular-nums tracking-tight">
                {progressPercent}%
              </p>
              <p className="text-[10px] text-foreground-muted font-bold uppercase tracking-wider">
                Estimated remaining: {remainingTime}s
              </p>
            </div>
          )}
          
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-5"
          >
            <div className="flex justify-between items-center border-b border-border/40 pb-3">
              <div>
                <h3 className="text-sm font-bold text-foreground">
                  {isAnimating ? "Deploying Code..." : isFailed ? "Deployment Failed" : "Pipeline Completed"}
                </h3>
                <p className="text-[10px] text-foreground-muted font-semibold mt-0.5">
                  {liveStatusText}
                </p>
              </div>
              {isAnimating && (
                <div className="w-24 bg-background-secondary border border-border/40 rounded-full h-1.5 overflow-hidden">
                  <motion.div
                    className="bg-primary h-full rounded-full"
                    initial={{ width: "0%" }}
                    animate={{ width: `${progressPercent}%` }}
                    transition={{ duration: 0.5 }}
                  />
                </div>
              )}
            </div>

            {/* stages mapping */}
            <div className="flex items-center justify-between overflow-x-auto pb-4 gap-4 no-scrollbar">
              {uiSteps.map((step, index) => (
                <div key={step.id} className="flex items-center flex-shrink-0">
                  <div className="flex flex-col items-center min-w-[90px]">
                    <div
                      className={`w-11 h-11 rounded-full flex items-center justify-center mb-2 border transition-all duration-300 ${
                        step.status === "completed"
                          ? "bg-success/15 border-success/30 text-success glow-green"
                          : step.status === "active"
                          ? "bg-primary/15 border-primary/30 text-primary animate-pulse"
                          : "bg-card border-border text-foreground-muted"
                      }`}
                    >
                      {step.status === "completed" ? (
                        <Check size={16} />
                      ) : step.status === "active" ? (
                        <Loader size={16} className="animate-spin" />
                      ) : (
                        <Circle size={12} className="text-foreground-muted" />
                      )}
                    </div>
                    <span
                      className={`text-[9px] font-bold text-center leading-snug max-w-[85px] whitespace-normal ${
                        step.status === "pending" ? "text-foreground-muted" : "text-foreground"
                      }`}
                    >
                      {step.label}
                    </span>
                    {step.duration && (
                      <span className="text-[8px] text-foreground-muted font-mono mt-0.5">
                        {step.duration}
                      </span>
                    )}
                  </div>
                  {index < uiSteps.length - 1 && (
                    <div
                      className={`h-px w-6 mx-1 transition-colors duration-300 ${
                        step.status === "completed" ? "bg-success/40" : "bg-border"
                      }`}
                    />
                  )}
                </div>
              ))}
            </div>
          </motion.div>

          {/* Logs container (collapsible) */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-card border border-border rounded-xl overflow-hidden shadow-sm"
          >
            <button
              onClick={() => setLogsCollapsed((c) => !c)}
              className="w-full flex items-center justify-between px-4 py-3 border-b border-border bg-background-secondary/40 text-[10px] text-foreground-muted hover:bg-card-hover/40 transition cursor-pointer"
            >
              <span className="font-mono">build-log</span>
              <span className="flex items-center gap-1">
                {isAnimating && <Loader2 size={10} className="animate-spin text-primary mr-2" />}
                {logsCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
              </span>
            </button>

            {!logsCollapsed && (
              <div
                ref={termRef}
                className="p-4 font-mono text-[11px] leading-6 h-[300px] overflow-y-auto no-scrollbar bg-zinc-950 text-zinc-100 shadow-inner"
              >
                {activeLines.slice(0, visibleLines).map((line, index) => (
                  <div key={index}>
                    {line.type === "blank" ? <br /> : <p className={lineColor(line.type)}>{line.text}</p>}
                  </div>
                ))}
                {activeLines.length === 0 && <p className="text-zinc-500">No logs recorded yet.</p>}
              </div>
            )}
          </motion.div>
        </>
      )}

      {/* Deployment History */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-card border border-border rounded-xl p-6 shadow-sm"
      >
        <h3 className="text-sm font-bold mb-4 text-foreground">Deployment History</h3>
        {historyLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-primary" />
          </div>
        ) : history.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <FolderGit2 className="w-10 h-10 text-foreground-muted/20 mb-3" />
            <p className="text-sm text-foreground-muted mb-1">No deployments yet</p>
            <p className="text-xs text-foreground-muted/60">Deploy your first project to see history here</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-foreground-muted border-b border-border text-xs">
                <th className="text-left py-3 font-semibold">App</th>
                <th className="text-left py-3 font-semibold">Version</th>
                <th className="text-left py-3 font-semibold">Env</th>
                <th className="text-left py-3 font-semibold">Status</th>
                <th className="text-left py-3 font-semibold">Duration</th>
                <th className="text-left py-3 font-semibold">Deployed By</th>
              </tr>
            </thead>
            <tbody>
              {history.map((deployment) => (
                <tr
                  key={deployment.id}
                  onClick={() =>
                    router.push(
                      `/dashboard/deployments?id=${deployment.id}&repo=${encodeURIComponent(
                        deployment.project_name || ""
                      )}`
                    )
                  }
                  className="border-b border-border/50 hover:bg-card-hover/30 transition-colors text-xs cursor-pointer"
                >
                  <td className="py-3 font-bold text-foreground">{deployment.project_name || "Project"}</td>
                  <td className="py-3 text-foreground-muted font-mono">{deployment.version || "Not recorded"}</td>
                  <td className="py-3 text-foreground-muted">{deployment.environment}</td>
                  <td className="py-3">
                    <StatusBadge status={deployment.status} />
                  </td>
                  <td className="py-3 text-foreground-muted">{deployment.duration || "Not recorded"}</td>
                  <td className="py-3 text-foreground-muted">{deployment.deployed_by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </motion.div>

      {/* Autoscaling modal */}
      {isScaleModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-card max-w-md w-full p-6 rounded-xl border border-border shadow-2xl relative"
          >
            <h3 className="text-lg font-bold mb-2">Scale Deployment</h3>
            <p className="text-xs text-foreground-muted mb-6">
              Adjust the replica target through the backend autoscaling endpoint.
            </p>
            <div className="flex items-center justify-between bg-card/40 border border-border rounded-lg p-4 mb-6">
              <span className="text-sm font-semibold">Replica Count</span>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setScaleCount(Math.max(1, scaleCount - 1))}
                  className="w-8 h-8 rounded-lg bg-card border border-border hover:bg-card-hover transition flex items-center justify-center font-bold cursor-pointer"
                >
                  -
                </button>
                <span className="text-lg font-bold w-6 text-center">{scaleCount}</span>
                <button
                  onClick={() => setScaleCount(Math.min(20, scaleCount + 1))}
                  className="w-8 h-8 rounded-lg bg-card border border-border hover:bg-card-hover transition flex items-center justify-center font-bold cursor-pointer"
                >
                  +
                </button>
              </div>
            </div>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setIsScaleModalOpen(false)}
                className="px-4 py-2 border border-border rounded-lg text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={executeScale}
                className="px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-xs font-semibold transition cursor-pointer"
              >
                Confirm Scale
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}

export default function DeploymentsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-[400px]">
          <Loader2 className="animate-spin text-primary" size={32} />
        </div>
      }
    >
      <DeploymentsPageContent />
    </Suspense>
  );
}
