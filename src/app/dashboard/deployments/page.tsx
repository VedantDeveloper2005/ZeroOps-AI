"use client";

import { motion } from "framer-motion";
import { useCallback, useState, useEffect, useRef, Suspense } from "react";
import { Check, Loader, Circle, RefreshCw, RotateCcw, Maximize, Rocket, Brain, Box, Cloud, Shield, TrendingUp, Globe, Lock, Loader2, GitBranch, Server, Network, Activity, Cpu } from "lucide-react";
import { deploymentSteps, deployments, terminalLines, Deployment } from "@/lib/mock-data";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useNotifications } from "@/lib/NotificationContext";
import { useSearchParams, useRouter } from "next/navigation";
import {
  createDeploymentRecord,
  createSimulatedDeploymentLines,
  liveUrlForProject,
  namespaceForProject,
  normalizeProjectId,
} from "@/lib/demo-runtime";
import { getWebSocketUrl } from "@/lib/runtime-config";

const stepIcons = [GitBranch, Cloud, Brain, Box, Cpu, Network, Server, Box, Activity, Check];

function DeploymentsPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const deployId = searchParams.get("id");
  const repoParam = searchParams.get("repo") || "acme/web-app";
  const projectId = normalizeProjectId(repoParam);

  const { addToast, addNotification, setHasDeployed } = useNotifications();
  const [steps, setSteps] = useState(deploymentSteps);
  const [activeLines, setActiveLines] = useState<Array<{ text: string; type: "command" | "blank" | "info" | "success" | "warning" | "error" }>>([]);
  const [visibleLines, setVisibleLines] = useState(0);
  const [history, setHistory] = useState<Deployment[]>([]);
  const [isScaleModalOpen, setIsScaleModalOpen] = useState(false);
  const [scaleCount, setScaleCount] = useState(4);
  const [isAnimating, setIsAnimating] = useState(true);
  const termRef = useRef<HTMLDivElement>(null);

  // Fetch deployment history
  const fetchHistory = useCallback(() => {
    fetch("/api/deployments")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch deployments");
        return res.json();
      })
      .then((data) => setHistory(data))
      .catch((err) => {
        console.error("Failed to load deployment history; using local demo history:", err);
        const localRecord = createDeploymentRecord(repoParam, deployId || undefined);
        setHistory([{ ...localRecord, status: "running", duration: "1m 15s" } as Deployment, ...deployments]);
      });
  }, [deployId, repoParam]);

  const runFallbackDeployment = useCallback((reason: string) => {
    const fallbackLines = createSimulatedDeploymentLines(repoParam);
    setActiveLines([{ text: reason, type: "warning" as const }]);
    setVisibleLines(1);
    setIsAnimating(true);
    setSteps(deploymentSteps.map((step) => ({ ...step, status: "pending" as const, duration: "" })));

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
      setSteps(deploymentSteps.map((step) => ({ ...step, status: "completed" as const, duration: step.duration || "done" })));
      setIsAnimating(false);
      setHasDeployed(true);
      const localRecord = createDeploymentRecord(repoParam, deployId || undefined);
      setHistory((prev) => [
        { ...localRecord, status: "running", duration: "1m 15s" } as Deployment,
        ...prev.filter((item) => item.id !== localRecord.id),
      ]);
      addToast("Guided deployment completed successfully.", "success");
      addNotification({
        title: "Deployment Successful",
        message: `${projectId} is healthy in ${namespaceForProject(projectId)} at ${liveUrlForProject(projectId)}.`,
        type: "success",
      });
    }, 180 * (fallbackLines.length + 2));
  }, [addNotification, addToast, deployId, projectId, repoParam, setHasDeployed]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  // Handle live WebSocket deployment stream or mock typewriter animation
  useEffect(() => {
    if (!deployId) {
      // Mock Mode: Initialize steps and terminal lines to mock data
      const timer = setTimeout(() => {
        setSteps(deploymentSteps);
        setActiveLines(terminalLines);
        setIsAnimating(true);
      }, 0);
      return () => clearTimeout(timer);
    }

    if (searchParams.get("mode") === "fallback") {
      const timer = window.setTimeout(() => {
        runFallbackDeployment("Backend unavailable. Running guided ZeroOps deployment simulation.");
      }, 0);
      return () => window.clearTimeout(timer);
    }

    // Live Mode: Reset steps to pending, connect to websocket
    const timer = setTimeout(() => {
      setSteps(
        deploymentSteps.map((s) =>
          s.id === 1
            ? { ...s, status: "active", duration: "..." }
            : { ...s, status: "pending", duration: "" }
        )
      );
      setActiveLines([
        { text: "Connecting to ZeroOps deployment stream...", type: "info" as const },
      ]);
      setVisibleLines(1);
      setIsAnimating(true);
    }, 0);

    const socket = new WebSocket(getWebSocketUrl(`/ws/deployments/${deployId}`));

    socket.onopen = () => {
      console.log(`Connected to deployments websocket for: ${deployId}`);
      setActiveLines((prev) => [
        ...prev,
        { text: `✓ Connected to host pipeline stream: ${deployId}`, type: "success" as const },
      ]);
      setVisibleLines((prev) => prev + 1);
    };

    socket.onmessage = (event) => {
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
            setHasDeployed(true);
            addNotification({
              title: "Deployment Successful",
              message: `Successfully deployed application for run ${deployId} to AKS.`,
              type: "success",
            });
          } else if (data.status === "failed") {
            addToast("Deployment failed! Check the build logs.", "error");
            addNotification({
              title: "Deployment Failed",
              message: `Pipeline run ${deployId} failed during execution.`,
              type: "critical",
            });
          }
          fetchHistory();
        }
      } catch (e) {
        console.error("Error parsing WS message:", e);
      }
    };

    socket.onerror = (err) => {
      console.error("WS connection error:", err);
      socket.close();
      runFallbackDeployment("WebSocket unavailable. Replaying a deterministic deployment stream.");
    };

    socket.onclose = () => {
      console.log("WebSocket connection closed");
      setIsAnimating(false);
    };

    return () => {
      clearTimeout(timer);
      socket.close();
    };
  }, [deployId, addNotification, addToast, repoParam, searchParams, projectId, runFallbackDeployment, fetchHistory]);

  // Typewriter effect for mock mode
  useEffect(() => {
    if (deployId) return; // Only run in mock mode
    const max = activeLines.length;
    let current = 0;
    const timer = setInterval(() => {
      current += 1;
      if (current >= max) {
        clearInterval(timer);
        setIsAnimating(false);
      }
      setVisibleLines(current);
    }, 60);
    return () => clearInterval(timer);
  }, [activeLines, deployId]);

  // Auto-scroll terminal
  useEffect(() => {
    if (termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight;
    }
  }, [visibleLines]);

  const handleRedeploy = async () => {
    if (isAnimating) return;
    addToast(`Initializing redeployment for ${projectId}...`, "info");
    try {
      const res = await fetch("/api/deployments/deploy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo: "acme/web-app", branch: "main" }),
      });
      if (!res.ok) throw new Error("Failed to redeploy");
      const data = await res.json();
      if (data.status === "success") {
        addToast("Redeployment initialized. Redirecting to live pipeline...", "success");
        router.push(`/dashboard/deployments?id=${data.deployment_id}&repo=${encodeURIComponent(repoParam)}`);
      }
    } catch (err) {
      console.error(err);
      addToast("Backend unavailable. Starting guided redeployment simulation.", "warning");
      router.push(`/dashboard/deployments?id=demo-${projectId}&repo=${encodeURIComponent(repoParam)}&mode=fallback`);
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
      { text: "  🌐 URL:     https://web-app.zeroops.dev", type: "info" as const },
      { text: "  📦 Image:   acr.azurecr.io/web:v2.4.0", type: "info" as const },
    ];
    setActiveLines(rollbackLogs);

    setTimeout(() => {
      addToast("Rollback completed successfully!", "success");
      addNotification({
        title: "Rollback Executed",
        message: `Successfully rolled back ${projectId} to version v2.4.0.`,
        type: "warning",
      });
    }, 1500);
  };

  const executeScale = async () => {
    setIsScaleModalOpen(false);
    addToast(`Scaling ${projectId} to ${scaleCount} replicas...`, "info");
    try {
      const res = await fetch("/api/deployments/scale", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "web-app", replicas: scaleCount }),
      });
      if (!res.ok) throw new Error("Failed to scale deployment");

      addToast(`Scaled to ${scaleCount} replicas successfully!`, "success");
      addNotification({
        title: "Scaling Event Complete",
        message: `Successfully scaled ${projectId} replicas: 4 -> ${scaleCount}.`,
        type: "info",
      });

      if (!deployId) {
        setVisibleLines(0);
        setIsAnimating(true);
        const scaleLogs = [
          { text: `$ zeroops scale --replicas ${scaleCount}`, type: "command" as const },
          { text: "", type: "blank" as const },
          { text: `▸ Updating ReplicaSet target replica count to ${scaleCount}...`, type: "info" as const },
          { text: "  ✓ Scaling target set. Scaling events initiated.", type: "success" as const },
          { text: "▸ Running cluster health audit...", type: "info" as const },
          { text: `  ✓ All ${scaleCount} replicas healthy and ready.`, type: "success" as const },
          { text: "", type: "blank" as const },
          { text: "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", type: "info" as const },
          { text: `✅ Scale execution complete. Active replicas: ${scaleCount}`, type: "success" as const },
        ];
        setActiveLines(scaleLogs);
      }
    } catch (err) {
      console.error(err);
      addToast("Scaling failed to execute on Kubernetes context.", "error");
    }
  };

  const lineColor = (type: string) => {
    switch (type) {
      case "command":
        return "text-white font-bold";
      case "success":
        return "text-green-400";
      case "warning":
        return "text-amber-400";
      case "error":
        return "text-red-400";
      default:
        return "text-foreground-muted";
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Deployments</h1>
          <p className="text-foreground-muted text-sm mt-1">Live deployment pipeline and history</p>
        </div>
        <div className="flex gap-2">
          <button
            disabled={isAnimating}
            onClick={handleRedeploy}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium bg-primary/10 text-primary hover:bg-primary/20 disabled:opacity-50 transition cursor-pointer"
          >
            <RefreshCw size={14} className={isAnimating && activeLines === terminalLines ? "animate-spin" : ""} />
            Redeploy
          </button>

          <button
            disabled={isAnimating}
            onClick={handleRollback}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium bg-warning/10 text-warning hover:bg-warning/20 disabled:opacity-50 transition cursor-pointer"
          >
            <RotateCcw size={14} />
            Rollback
          </button>

          <button
            disabled={isAnimating}
            onClick={() => setIsScaleModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium bg-accent/10 text-accent hover:bg-accent/20 disabled:opacity-50 transition cursor-pointer"
          >
            <Maximize size={14} />
            Scale
          </button>
        </div>
      </div>

      {/* Pipeline */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-xl p-6">
        <h3 className="font-semibold mb-6">Active Deployment Pipeline</h3>
        <div className="flex items-center justify-between overflow-x-auto pb-4">
          {steps.map((step, i) => {
            const Icon = stepIcons[i] || Circle;
            return (
              <div key={step.id} className="flex items-center flex-shrink-0">
                <div className="flex flex-col items-center min-w-[80px]">
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ delay: i * 0.1 }}
                    className={`w-12 h-12 rounded-full flex items-center justify-center mb-2 ${
                      step.status === "completed"
                        ? "bg-success/10 border border-success/30"
                        : step.status === "active"
                        ? "bg-primary/10 border border-primary/30"
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
                  <span
                    className={`text-xs font-medium text-center ${
                      step.status === "pending" ? "text-foreground-muted" : "text-foreground"
                    }`}
                  >
                    {step.label}
                  </span>
                  {step.duration && <span className="text-[10px] text-foreground-muted mt-0.5">{step.duration}</span>}
                </div>
                {i < steps.length - 1 && (
                  <div className={`h-px w-8 mx-1 ${step.status === "completed" ? "bg-success/40" : "bg-border"}`} />
                )}
              </div>
            );
          })}
        </div>
        {/* Progress bar */}
        <div className="h-1.5 bg-card rounded-full overflow-hidden mt-4">
          <motion.div
            initial={{ width: "0%" }}
            animate={{ width: deployId ? `${(steps.filter(s => s.status === 'completed').length / steps.length) * 100}%` : "62%" }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            className="h-full bg-gradient-to-r from-primary to-accent rounded-full relative"
          >
            <div
              className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-[shimmer_2s_ease-in-out_infinite]"
              style={{ backgroundSize: "200% 100%" }}
            />
          </motion.div>
        </div>
      </motion.div>

      {/* Terminal */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass rounded-xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
          <div className="w-3 h-3 rounded-full bg-red-500/80" />
          <div className="w-3 h-3 rounded-full bg-amber-500/80" />
          <div className="w-3 h-3 rounded-full bg-green-500/80" />
          <span className="text-xs text-foreground-muted ml-2 font-mono">deployment-log</span>
          {isAnimating && <Loader2 size={12} className="animate-spin text-primary ml-auto" />}
        </div>
        <div ref={termRef} className="p-4 font-mono text-xs leading-6 h-[300px] overflow-y-auto no-scrollbar bg-black/40">
          {activeLines.slice(0, visibleLines).map((line, i) => (
            <div key={i}>{line.type === "blank" ? <br /> : <p className={lineColor(line.type)}>{line.text}</p>}</div>
          ))}
          {visibleLines < activeLines.length && <span className="inline-block w-2 h-4 bg-primary animate-pulse" />}
        </div>
      </motion.div>

      {/* History */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="glass rounded-xl p-6">
        <h3 className="font-semibold mb-4">Deployment History</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-foreground-muted border-b border-border">
              <th className="text-left py-3 font-medium">App</th>
              <th className="text-left py-3 font-medium">Version</th>
              <th className="text-left py-3 font-medium">Status</th>
              <th className="text-left py-3 font-medium">Duration</th>
              <th className="text-left py-3 font-medium">Time</th>
            </tr>
          </thead>
          <tbody>
            {(history.length > 0 ? history : deployments).map((d) => (
              <tr key={d.id} className="border-b border-border/50 hover:bg-card-hover/30 transition-colors">
                <td className="py-3 font-medium text-foreground">{d.app}</td>
                <td className="py-3 text-foreground-muted font-mono text-xs">{d.version}</td>
                <td className="py-3">
                  <StatusBadge status={d.status} />
                </td>
                <td className="py-3 text-foreground-muted">{d.duration}</td>
                <td className="py-3 text-foreground-muted">{d.time}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </motion.div>

      {/* Scale Modal */}
      {isScaleModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="glass max-w-md w-full p-6 rounded-xl border border-border shadow-2xl relative"
          >
            <h3 className="text-lg font-bold mb-2">Scale Deployment</h3>
            <p className="text-xs text-foreground-muted mb-6">
              Adjust the replica count for {projectId}. ZeroOps will autonomously partition and register pods.
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
                className="px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-xs font-semibold transition glow-blue cursor-pointer"
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
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="animate-spin text-primary" size={32} />
      </div>
    }>
      <DeploymentsPageContent />
    </Suspense>
  );
}
