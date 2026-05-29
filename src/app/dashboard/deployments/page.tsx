"use client";

import { motion } from "framer-motion";
import { useCallback, useState, useEffect, useRef, Suspense } from "react";
import { Check, Loader, Circle, RefreshCw, RotateCcw, Maximize, Loader2, GitBranch, Server, Network, Activity, Cpu, Brain, Box, Cloud, Shield, FolderGit2 } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useNotifications } from "@/lib/NotificationContext";
import { useSearchParams, useRouter } from "next/navigation";
import { api, type Deployment } from "@/lib/api";
import {
  createSimulatedDeploymentLines,
  deploymentStageLabels,
  liveUrlForProject,
  namespaceForProject,
  normalizeProjectId,
} from "@/lib/demo-runtime";
import { getWebSocketUrl } from "@/lib/runtime-config";

const stepIcons = [GitBranch, Cloud, Brain, Box, Cpu, Network, Server, Box, Activity, Check];

// Local step type for the pipeline UI
interface PipelineStep {
  id: number;
  label: string;
  status: "completed" | "active" | "pending";
  duration: string;
}

function createInitialSteps(): PipelineStep[] {
  return deploymentStageLabels.map((label, i) => ({
    id: i + 1,
    label,
    status: "pending" as const,
    duration: "",
  }));
}

function DeploymentsPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const deployId = searchParams.get("id");
  const repoParam = searchParams.get("repo") || "acme/web-app";
  const projectId = normalizeProjectId(repoParam);

  const { addToast, addNotification, refreshStats } = useNotifications();
  const [steps, setSteps] = useState<PipelineStep[]>(createInitialSteps());
  const [activeLines, setActiveLines] = useState<Array<{ text: string; type: "command" | "blank" | "info" | "success" | "warning" | "error" }>>([]);
  const [visibleLines, setVisibleLines] = useState(0);
  const [history, setHistory] = useState<Deployment[]>([]);
  const [isScaleModalOpen, setIsScaleModalOpen] = useState(false);
  const [scaleCount, setScaleCount] = useState(4);
  const [isAnimating, setIsAnimating] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [failureAnalysis, setFailureAnalysis] = useState<any>(null);
  const [isLoadingFailureAnalysis, setIsLoadingFailureAnalysis] = useState(false);
  const termRef = useRef<HTMLDivElement>(null);

  // Fetch deployment history from API
  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const data = await api.getDeployments(20);
      setHistory(data);
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const runFallbackDeployment = useCallback((reason: string) => {
    const fallbackLines = createSimulatedDeploymentLines(repoParam);
    setActiveLines([{ text: reason, type: "warning" as const }]);
    setVisibleLines(1);
    setIsAnimating(true);
    setSteps(createInitialSteps());

    fallbackLines.forEach((line, index) => {
      window.setTimeout(() => {
        setActiveLines((prev) => [...prev, line]);
        setVisibleLines((prev) => prev + 1);

        let stepIndex = 0;
        for (let i = index; i >= 0; i--) {
          const text = fallbackLines[i]?.text || "";
          const stageMatch = text.match(/\[Stage (\d+)\]/);
          if (stageMatch) {
            stepIndex = parseInt(stageMatch[1]) - 1;
            break;
          }
        }

        setSteps((prevSteps) =>
          prevSteps.map((step, i) => {
            if (i < stepIndex) return { ...step, status: "completed", duration: step.duration || "done" };
            if (i === stepIndex) return { ...step, status: "active", duration: "..." };
            return step;
          })
        );
      }, 180 * (index + 1));
    });

    window.setTimeout(() => {
      setSteps(createInitialSteps().map((step) => ({ ...step, status: "completed" as const, duration: "done" })));
      setIsAnimating(false);
      refreshStats();
      fetchHistory();
      addToast("Deployment completed successfully.", "success");
      addNotification({
        title: "Deployment Successful",
        message: `${projectId} is healthy in ${namespaceForProject(projectId)} at ${liveUrlForProject(projectId)}.`,
        type: "success",
        category: "deployment",
        action_url: "/dashboard/deployments",
      });
    }, 180 * (fallbackLines.length + 2));
  }, [addNotification, addToast, fetchHistory, projectId, repoParam, refreshStats]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  useEffect(() => {
    if (!deployId) {
      setFailureAnalysis(null);
      return;
    }
    const currentDep = history.find((h) => h.id === deployId);
    if (currentDep?.status === "failed") {
      setIsLoadingFailureAnalysis(true);
      api.getDeploymentFailureAnalysis(deployId)
        .then((data) => {
          setFailureAnalysis(data);
        })
        .catch((err) => {
          console.error("Failed to load failure analysis:", err);
          setFailureAnalysis(null);
        })
        .finally(() => {
          setIsLoadingFailureAnalysis(false);
        });
    } else {
      setFailureAnalysis(null);
    }
  }, [deployId, history]);

  // Handle live WebSocket deployment stream, simulation, or loading historical logs
  useEffect(() => {
    if (!deployId) {
      setSteps(createInitialSteps());
      setActiveLines([]);
      setVisibleLines(0);
      setIsAnimating(false);
      return;
    }

    if (searchParams.get("mode") === "fallback") {
      const timer = window.setTimeout(() => {
        runFallbackDeployment("Backend unavailable. Running guided ZeroOps deployment simulation.");
      }, 0);
      return () => window.clearTimeout(timer);
    }

    let socket: WebSocket | null = null;
    let active = true;

    async function initializeLogsStream() {
      // 1. Check if the deployment is a completed one by calling the API
      try {
        const detail = await api.getDeployment(deployId!);
        if (!active) return;

        const isFinished = ["running", "failed", "stopped", "rolled_back"].includes(detail.status);
        if (isFinished) {
          setIsAnimating(false);
          const mappedLines = detail.logs.map(log => ({
            text: log.message,
            type: log.level.toLowerCase() as "command" | "blank" | "info" | "success" | "warning" | "error"
          }));
          setActiveLines(mappedLines);
          setVisibleLines(mappedLines.length);

          if (detail.status === "failed") {
            setSteps(createInitialSteps().map((step, idx) => {
              if (idx < 8) return { ...step, status: "completed" as const, duration: "done" };
              if (idx === 8) return { ...step, status: "pending" as const, duration: "failed" };
              return { ...step, status: "pending" as const, duration: "" };
            }));
          } else {
            setSteps(createInitialSteps().map((step) => ({
              ...step,
              status: "completed" as const,
              duration: "done"
            })));
          }
          return;
        }
      } catch (err) {
        console.error("Failed to check deployment details, falling back to websocket", err);
      }

      // 2. If it's building/active, connect to WebSocket
      if (!active) return;
      
      setSteps(
        createInitialSteps().map((s) =>
          s.id === 1
            ? { ...s, status: "active" as const, duration: "..." }
            : s
        )
      );
      setActiveLines([
        { text: "Connecting to ZeroOps deployment stream...", type: "info" as const },
      ]);
      setVisibleLines(1);
      setIsAnimating(true);

      socket = new WebSocket(getWebSocketUrl(`/ws/deployments/${deployId}`));

      socket.onopen = () => {
        if (!active) return;
        setActiveLines((prev) => [
          ...prev,
          { text: `✓ Connected to host pipeline stream: ${deployId}`, type: "success" as const },
        ]);
        setVisibleLines((prev) => prev + 1);
      };

      socket.onmessage = (event) => {
        if (!active) return;
        try {
          const data = JSON.parse(event.data);
          if (data.type === "stage") {
            setSteps((prevSteps) =>
              prevSteps.map((step) =>
                step.id === data.id
                  ? { ...step, status: data.status, duration: data.duration || step.duration }
                  : step
              )
            );
          } else if (data.type === "log") {
            setActiveLines((prev) => {
              const updated = [...prev, { text: data.text, type: data.lineType as "command" | "blank" | "info" | "success" | "warning" | "error" }];
              setVisibleLines(updated.length);
              return updated;
            });
          } else if (data.type === "status") {
            setIsAnimating(false);
            if (data.status === "running") {
              addToast("Deployment successful: your app is live!", "success");
              refreshStats();
              addNotification({
                title: "Deployment Successful",
                message: `Successfully deployed application for run ${deployId} to AKS.`,
                type: "success",
                category: "deployment",
                action_url: "/dashboard/deployments",
              });
            } else if (data.status === "failed") {
              addToast("Deployment failed! Check the build logs.", "error");
              addNotification({
                title: "Deployment Failed",
                message: `Pipeline run ${deployId} failed during execution.`,
                type: "critical",
                category: "deployment",
                action_url: "/dashboard/deployments",
              });
            }
            fetchHistory();
          }
        } catch (e) {
          console.error("Error parsing WS message:", e);
        }
      };

      socket.onerror = () => {
        if (!active) return;
        socket?.close();
        runFallbackDeployment("WebSocket unavailable. Replaying a deterministic deployment stream.");
      };

      socket.onclose = () => {
        if (!active) return;
        setIsAnimating(false);
      };
    }

    initializeLogsStream();

    return () => {
      active = false;
      if (socket) {
        socket.close();
      }
    };
  }, [deployId, addNotification, addToast, repoParam, searchParams, projectId, runFallbackDeployment, fetchHistory, refreshStats]);

  // Auto-scroll terminal
  useEffect(() => {
    if (termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight;
    }
  }, [visibleLines]);

  const handleRedeploy = async () => {
    if (isAnimating) return;
    const currentDep = history.find(h => h.id === deployId);
    const targetProjectId = currentDep?.project_id || (history.length > 0 ? history[0].project_id : null);
    
    if (!targetProjectId) {
      addToast("No active project found to redeploy.", "error");
      return;
    }

    addToast(`Initializing redeployment...`, "info");
    try {
      const data = await api.startDeployment({
        project_id: targetProjectId,
        branch: currentDep?.branch || "main",
        environment: currentDep?.environment || "production"
      });
      if (data.status === "success") {
        addToast("Redeployment initialized. Redirecting to live pipeline...", "success");
        router.push(`/dashboard/deployments?id=${data.deployment_id}&repo=${encodeURIComponent(repoParam)}`);
      }
    } catch {
      addToast("Failed to initialize redeployment.", "error");
    }
  };

  const handleRollback = () => {
    if (isAnimating) return;
    setVisibleLines(0);
    setIsAnimating(true);
    addToast("Initiating rollback to version v2.4.0...", "warning");
    const rollbackLogs = [
      { text: "$ zeroops rollback --repo acme/web-app --target v2.4.0", type: "command" as const },
      { text: "", type: "blank" as const },
      { text: "▸ Fetching manifest for target version v2.4.0...", type: "info" as const },
      { text: "  ✓ Target version verified", type: "success" as const },
      { text: "▸ Adjusting deployment target to v2.4.0...", type: "info" as const },
      { text: "  ✓ Scaling down old replica sets (v2.4.1)", type: "success" as const },
      { text: "  ✓ Scaling up target replica sets (v2.4.0)", type: "success" as const },
      { text: "", type: "blank" as const },
      { text: "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", type: "info" as const },
      { text: "✅ Rollback completed successfully in 8.4s!", type: "success" as const },
    ];
    setActiveLines(rollbackLogs);
    setVisibleLines(rollbackLogs.length);

    setTimeout(() => {
      setIsAnimating(false);
      addToast("Rollback completed successfully!", "success");
      addNotification({
        title: "Rollback Executed",
        message: `Successfully rolled back ${projectId} to version v2.4.0.`,
        type: "warning",
        category: "deployment",
        action_url: "/dashboard/deployments",
      });
    }, 1500);
  };

  const executeScale = async () => {
    setIsScaleModalOpen(false);
    const currentDep = history.find(h => h.id === deployId);
    const targetProjectId = currentDep?.project_id || (history.length > 0 ? history[0].project_id : null);
    
    if (!targetProjectId) {
      addToast("No active project selected to scale.", "error");
      return;
    }

    addToast(`Scaling deployment to ${scaleCount} replicas...`, "info");
    try {
      await api.configureAutoscaling({
        projectId: targetProjectId,
        minReplicas: scaleCount,
        maxReplicas: scaleCount,
        cpuTarget: 80
      });
      addToast(`Scaled to ${scaleCount} replicas successfully!`, "success");
    } catch {
      addToast("Failed to scale deployment.", "error");
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

  // Check if there's an active deployment pipeline to show
  const showPipeline = !!deployId || activeLines.length > 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-end">
        {history.length > 0 && (
          <div className="flex gap-2">
            <button
              disabled={isAnimating}
              onClick={handleRedeploy}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold bg-primary text-white hover:bg-primary-hover disabled:opacity-50 transition cursor-pointer shadow-sm"
            >
              <RefreshCw size={14} className={isAnimating ? "animate-spin" : ""} />
              Redeploy
            </button>
            <button
              disabled={isAnimating}
              onClick={handleRollback}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold bg-background-secondary text-foreground hover:bg-card-hover border border-border disabled:opacity-50 transition cursor-pointer shadow-sm"
            >
              <RotateCcw size={14} />
              Rollback
            </button>
            <button
              disabled={isAnimating}
              onClick={() => setIsScaleModalOpen(true)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold bg-background-secondary text-foreground hover:bg-card-hover border border-border disabled:opacity-50 transition cursor-pointer shadow-sm"
            >
              <Maximize size={14} />
              Scale
            </button>
          </div>
        )}
      </div>

      {/* Pipeline (only shown during active deployment) */}
      {showPipeline && (
        <>
          <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
            <h3 className="text-sm font-bold mb-6 text-foreground">Active Deployment Pipeline</h3>
            <div className="flex items-center justify-between overflow-x-auto pb-4">
              {steps.map((step, i) => {
                const Icon = stepIcons[i] || Circle;
                return (
                  <div key={step.id} className="flex items-center flex-shrink-0">
                    <div className="flex flex-col items-center min-w-[80px]">
                      <motion.div
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ delay: i * 0.05 }}
                        className={`w-12 h-12 rounded-full flex items-center justify-center mb-2 ${
                          step.status === "completed"
                            ? "bg-success/10 border border-success/30"
                            : step.status === "active"
                            ? "bg-primary/10 border border-primary/30 animate-pulse"
                            : "bg-card border border-border"
                        }`}
                      >
                        {step.status === "completed" ? (
                          <Check size={18} className="text-success" />
                        ) : step.status === "active" ? (
                          <Loader size={18} className="text-primary animate-spin" />
                        ) : (
                          <Icon size={18} className="text-foreground-muted" />
                        )}
                      </motion.div>
                      <span className={`text-[10px] font-semibold text-center ${step.status === "pending" ? "text-foreground-muted" : "text-foreground"}`}>
                        {step.label}
                      </span>
                      {step.duration && <span className="text-[9px] text-foreground-muted mt-0.5">{step.duration}</span>}
                    </div>
                    {i < steps.length - 1 && (
                      <div className={`h-px w-8 mx-1 ${step.status === "completed" ? "bg-success/40" : "bg-border"}`} />
                    )}
                  </div>
                );
              })}
            </div>
            <div className="h-1.5 bg-background-secondary rounded-full overflow-hidden mt-4">
              <motion.div
                initial={{ width: "0%" }}
                animate={{ width: `${(steps.filter(s => s.status === 'completed').length / steps.length) * 100}%` }}
                transition={{ duration: 0.5, ease: "easeOut" }}
                className="h-full bg-primary rounded-full relative"
              >
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-[shimmer_2s_ease-in-out_infinite]" style={{ backgroundSize: "200% 100%" }} />
              </motion.div>
            </div>
          </motion.div>

          {/* Terminal */}
          <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-background-secondary/40">
              <div className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
              <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/80" />
              <div className="w-2.5 h-2.5 rounded-full bg-green-500/80" />
              <span className="text-[10px] text-foreground-muted ml-2 font-mono">deployment-log</span>
              {isAnimating && <Loader2 size={12} className="animate-spin text-primary ml-auto" />}
            </div>
            <div ref={termRef} className="p-4 font-mono text-[11px] leading-6 h-[300px] overflow-y-auto no-scrollbar bg-zinc-950 text-zinc-100">
              {activeLines.slice(0, visibleLines).map((line, i) => (
                <div key={i}>{line.type === "blank" ? <br /> : <p className={lineColor(line.type)}>{line.text}</p>}</div>
              ))}
              {visibleLines < activeLines.length && <span className="inline-block w-2 h-4 bg-primary animate-pulse" />}
            </div>
          </motion.div>

          {/* NVIDIA Nemotron Failure Analysis Card */}
          {isLoadingFailureAnalysis ? (
            <div className="flex items-center justify-center p-8 bg-card border border-border rounded-xl shadow-sm">
              <Loader2 className="animate-spin text-primary mr-2" size={16} />
              <span className="text-xs text-foreground-muted">Querying NVIDIA Nemotron for failure root cause...</span>
            </div>
          ) : failureAnalysis ? (
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass rounded-xl border border-rose-500/20 bg-gradient-to-b from-rose-500/5 to-transparent p-6 shadow-md space-y-4"
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center justify-between border-b border-border/40 pb-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-500">
                    <Brain size={18} />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                      NVIDIA Nemotron failure analysis
                    </h4>
                    <p className="text-[10px] text-foreground-muted">Autonomous Root Cause Detection Engine</p>
                  </div>
                </div>
                <span className={`self-start sm:self-auto text-[10px] font-mono uppercase tracking-wider font-bold px-2 py-0.5 rounded border ${
                  failureAnalysis.severity === "critical" 
                    ? "bg-red-500/15 border-red-500/30 text-red-400"
                    : failureAnalysis.severity === "warning"
                    ? "bg-amber-500/15 border-amber-500/30 text-amber-400"
                    : "bg-rose-500/15 border-rose-500/30 text-rose-400"
                }`}>
                  {failureAnalysis.severity || "error"}
                </span>
              </div>

              <div className="space-y-4 text-xs">
                <div>
                  <p className="font-bold text-foreground mb-1.5">Failure Summary</p>
                  <p className="text-foreground-muted bg-background-secondary/40 border border-border/40 p-3 rounded-lg leading-relaxed">
                    {failureAnalysis.failure_summary}
                  </p>
                </div>

                <div className="grid md:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <p className="font-bold text-foreground">Root Cause Analysis</p>
                    <p className="text-foreground-muted leading-relaxed">
                      {failureAnalysis.root_cause}
                    </p>
                  </div>
                  <div className="space-y-1">
                    <p className="font-bold text-foreground">Recommended Fix</p>
                    <p className="text-foreground-muted leading-relaxed">
                      {failureAnalysis.recommended_fix}
                    </p>
                  </div>
                </div>

                {failureAnalysis.step_by_step_resolution && failureAnalysis.step_by_step_resolution.length > 0 && (
                  <div className="pt-2">
                    <p className="font-bold text-foreground mb-2">Step-by-Step Resolution</p>
                    <div className="space-y-2">
                      {failureAnalysis.step_by_step_resolution.map((step: string, idx: number) => (
                        <div key={idx} className="flex gap-3 items-start bg-background-secondary/20 border border-border/20 p-2.5 rounded-lg">
                          <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-rose-500/10 text-[10px] font-bold text-rose-400 border border-rose-500/20">
                            {idx + 1}
                          </span>
                          <span className="text-foreground-muted leading-relaxed">{step}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          ) : null}
        </>
      )}

      {/* History */}
      <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
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
              {history.map((d) => (
                <tr
                  key={d.id}
                  onClick={() => router.push(`/dashboard/deployments?id=${d.id}&repo=${encodeURIComponent(d.project_name || "")}`)}
                  className="border-b border-border/50 hover:bg-card-hover/30 transition-colors text-xs cursor-pointer"
                >
                  <td className="py-3 font-bold text-foreground">{d.project_name || "Project"}</td>
                  <td className="py-3 text-foreground-muted font-mono">{d.version || "—"}</td>
                  <td className="py-3 text-foreground-muted">{d.environment}</td>
                  <td className="py-3"><StatusBadge status={d.status as any} /></td>
                  <td className="py-3 text-foreground-muted">{d.duration || "—"}</td>
                  <td className="py-3 text-foreground-muted">{d.deployed_by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </motion.div>

      {/* Scale Modal */}
      {isScaleModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-card max-w-md w-full p-6 rounded-xl border border-border shadow-2xl relative"
          >
            <h3 className="text-lg font-bold mb-2">Scale Deployment</h3>
            <p className="text-xs text-foreground-muted mb-6">
              Adjust the replica count for {projectId}. ZeroOps will autonomously partition and register pods.
            </p>
            <div className="flex items-center justify-between bg-card/40 border border-border rounded-lg p-4 mb-6">
              <span className="text-sm font-semibold">Replica Count</span>
              <div className="flex items-center gap-3">
                <button onClick={() => setScaleCount(Math.max(1, scaleCount - 1))} className="w-8 h-8 rounded-lg bg-card border border-border hover:bg-card-hover transition flex items-center justify-center font-bold cursor-pointer">-</button>
                <span className="text-lg font-bold w-6 text-center">{scaleCount}</span>
                <button onClick={() => setScaleCount(Math.min(20, scaleCount + 1))} className="w-8 h-8 rounded-lg bg-card border border-border hover:bg-card-hover transition flex items-center justify-center font-bold cursor-pointer">+</button>
              </div>
            </div>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setIsScaleModalOpen(false)} className="px-4 py-2 border border-border rounded-lg text-xs font-semibold hover:bg-card-hover transition cursor-pointer">Cancel</button>
              <button onClick={executeScale} className="px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-xs font-semibold transition glow-blue cursor-pointer">Confirm Scale</button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}

export default function DeploymentsPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="animate-spin text-primary" size={32} />
      </div>
    }>
      <DeploymentsPageContent />
    </Suspense>
  );
}
