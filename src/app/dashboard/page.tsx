"use client";

import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, ArrowUpRight, Rocket, Shield, Terminal, GitBranch, Brain, Cpu, Zap, Loader2, Check, Lock, Play, ArrowRight } from "lucide-react";
import { dashboardStats as initialStats, deployments, trafficMetrics } from "@/lib/mock-data";
import { AreaChart } from "@/components/ui/AreaChart";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useState } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { useRouter } from "next/navigation";

const timeRanges = ["1h", "6h", "24h", "7d"];
const statIcons: Record<string, React.ElementType> = { blue: Rocket, green: Shield, cyan: Zap, purple: Brain, amber: Cpu, red: TrendingDown };

interface RecommendationItem {
  id: string;
  icon: React.ElementType;
  title: string;
  desc: string;
  color: string;
  savings: number;
}

export default function DashboardHome() {
  const router = useRouter();
  const { addToast, addNotification, hasDeployed } = useNotifications();
  const [timeRange, setTimeRange] = useState("24h");
  const [stats, setStats] = useState(initialStats);
  const [recs] = useState<RecommendationItem[]>([
    { id: "rec-1", icon: TrendingUp, title: "Optimize api-gateway scaling", desc: "Reduce CPU allocation 500m→200m", color: "text-primary", savings: 18 },
    { id: "rec-2", icon: Shield, title: "Patch CVE-2026-1234", desc: "Critical vulnerability in base image", color: "text-danger", savings: 0 },
    { id: "rec-3", icon: Cpu, title: "Reduce staging costs", desc: "3 idle pods detected — save $22/mo", color: "text-warning", savings: 22 },
  ]);

  if (!hasDeployed) {
    return (
      <div className="space-y-8">
        {/* Onboarding Hero Banner */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          className="relative rounded-2xl overflow-hidden glass border border-primary/20 p-8 md:p-10 flex flex-col md:flex-row items-center justify-between gap-8 shadow-2xl"
        >
          {/* Subtle decorative glow */}
          <div className="absolute top-0 left-1/4 w-96 h-96 bg-primary/10 rounded-full blur-3xl opacity-60 pointer-events-none" />
          <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-accent/5 rounded-full blur-3xl opacity-60 pointer-events-none" />

          <div className="relative z-10 space-y-4 max-w-2xl text-center md:text-left">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary border border-primary/20 text-xs font-semibold">
              <Zap size={12} className="animate-pulse" />
              SaaS Deployment Sandbox Active
            </div>
            <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight bg-gradient-to-r from-foreground via-foreground/90 to-foreground-muted bg-clip-text text-transparent">
              Deploy Your First Application
            </h1>
            <p className="text-foreground-muted text-sm md:text-base leading-relaxed">
              ZeroOps AI connects directly to your code repo, auto-detects frameworks (Next.js, FastAPI, NestJS), runs cognitive dependency analysis, compiles isolated Docker environments, and provisions Kubernetes clusters instantly.
            </p>
            <div className="pt-2 flex flex-col sm:flex-row justify-center md:justify-start gap-4">
              <button
                onClick={() => router.push("/dashboard/repositories")}
                className="flex items-center justify-center gap-2 px-6 py-3 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary-hover transition-all glow-blue cursor-pointer group"
              >
                <Rocket size={16} />
                Get Started
                <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform" />
              </button>
            </div>
          </div>

          <div className="relative z-10 flex-shrink-0 w-48 h-48 md:w-64 md:h-64 flex items-center justify-center bg-card/40 rounded-2xl border border-border/60 shadow-inner overflow-hidden select-none">
            {/* Mock abstract server/deployment visualizer */}
            <div className="absolute inset-0 bg-[radial-gradient(#ffffff0a_1px,transparent_1px)] [background-size:16px_16px] opacity-60" />
            <div className="w-24 h-24 rounded-full border-2 border-dashed border-primary/30 flex items-center justify-center relative animate-[spin_30s_linear_infinite]">
              <div className="w-16 h-16 rounded-full border border-dashed border-accent/40 flex items-center justify-center">
                <GitBranch size={20} className="text-foreground-muted" />
              </div>
            </div>
            <div className="absolute bottom-4 left-4 right-4 text-center">
              <span className="text-[10px] font-mono text-foreground-muted">Awaiting connection...</span>
            </div>
          </div>
        </motion.div>

        {/* AI Assistant Intro + Operations Checklist */}
        <div className="grid md:grid-cols-3 gap-6">
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="md:col-span-2 glass rounded-2xl p-6 border border-border/40 flex flex-col justify-between"
          >
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center">
                  <Brain size={20} className="text-accent" />
                </div>
                <div>
                  <h3 className="font-bold text-foreground">Cognitive Orchestrator</h3>
                  <p className="text-xs text-foreground-muted">ZeroOps Autonomous AI Agent</p>
                </div>
              </div>
              <p className="text-sm text-foreground-muted leading-relaxed">
                ZeroOps AI continuously inspects cluster states, scales pods based on traffic forecasts, blocks DDoS attempts, and patches Docker runtime vulnerabilities. Once your first container goes live, our Cognitive Orchestrator will activate and populate this dashboard with recommendations.
              </p>
            </div>
            
            <div className="mt-6 p-4 rounded-xl bg-black/10 border border-border/20 flex items-center justify-between">
              <div className="flex items-center gap-3 text-xs text-foreground-muted">
                <span className="flex h-2 w-2 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-accent"></span>
                </span>
                Cognitive agent standby: awaiting active deployment manifest
              </div>
              <span className="text-[10px] font-mono text-foreground-muted/60">v1.2.0-core</span>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="glass rounded-2xl p-6 border border-border/40"
          >
            <h3 className="font-bold text-foreground mb-4">Onboarding Progress</h3>
            <div className="space-y-4">
              {[
                { label: "Connect Git Repository", desc: "Link GitHub branch", done: false, active: true },
                { label: "Cognitive Code Analysis", desc: "Auto-detect runtimes & ports", done: false, active: false },
                { label: "Configure Infrastructure", desc: "Define env vars & region limits", done: false, active: false },
                { label: "Verify Pipeline Health", desc: "AKS liveness/readiness probes", done: false, active: false },
                { label: "Production Monitoring", desc: "Unlock live logs & analytics", done: false, active: false },
              ].map((step, i) => (
                <div key={i} className="flex gap-3 items-start">
                  <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold border mt-0.5 ${
                    step.done 
                      ? "bg-success/20 border-success text-success" 
                      : step.active 
                      ? "bg-primary/20 border-primary text-primary animate-pulse" 
                      : "bg-card border-border text-foreground-muted"
                  }`}>
                    {i + 1}
                  </div>
                  <div>
                    <p className={`text-xs font-semibold ${step.active ? "text-foreground" : "text-foreground-muted"}`}>
                      {step.label}
                    </p>
                    <p className="text-[10px] text-foreground-muted">{step.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>

        {/* Blurred Topology and Placeholder Metrics */}
        <div className="space-y-4">
          <h3 className="font-semibold text-foreground">Infrastructure Overview</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              { label: "Cluster CPU Load", val: "-- %", desc: "Awaiting pods deployment" },
              { label: "Active Memory Util", val: "-- MiB", desc: "No containers provisioned" },
              { label: "Live Traffic Rate", val: "-- req/s", desc: "No ingress mapping" }
            ].map((p, i) => (
              <div key={i} className="glass rounded-xl p-5 relative overflow-hidden group">
                <div className="absolute inset-0 bg-background/40 backdrop-blur-[2px] z-10 flex flex-col items-center justify-center text-center p-4">
                  <Lock size={16} className="text-foreground-muted/60 mb-1.5" />
                  <span className="text-[10px] font-mono tracking-widest text-foreground-muted/50 uppercase">Locked</span>
                </div>
                <div className="opacity-20 space-y-2 select-none">
                  <p className="text-xs text-foreground-muted">{p.label}</p>
                  <p className="text-2xl font-bold text-foreground">{p.val}</p>
                  <p className="text-[10px] text-foreground-muted">{p.desc}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="glass rounded-2xl p-6 border border-border/40 relative overflow-hidden min-h-[220px] flex items-center justify-center">
            <div className="absolute inset-0 bg-background/40 backdrop-blur-[3px] z-10 flex flex-col items-center justify-center text-center p-6">
              <div className="w-12 h-12 rounded-xl bg-card border border-border/60 flex items-center justify-center mb-3">
                <Lock size={20} className="text-foreground-muted/80" />
              </div>
              <h4 className="text-sm font-bold text-foreground">Interactive Topology Map Locked</h4>
              <p className="text-xs text-foreground-muted max-w-md mt-1">
                ZeroOps generates active topological node views of your Kubernetes namespaces dynamically. Complete your first deployment to visualize ingress flows and node distributions.
              </p>
            </div>
            
            {/* Mock abstract canvas bg */}
            <div className="w-full opacity-10 flex justify-around items-center select-none py-10 font-mono text-[9px] text-foreground-muted">
              <div>[Node: aks-agentpool-3490-vmss]</div>
              <div className="h-10 w-px bg-foreground-muted" />
              <div>[Pod: api-gateway-0a1b-74df]</div>
              <div className="h-10 w-px bg-foreground-muted" />
              <div>[Service: web-app-svc]</div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const [applyingId, setApplyingId] = useState<string | null>(null);
  const [completedIds, setCompletedIds] = useState<string[]>([]);
  const [runningAction, setRunningAction] = useState<string | null>(null);

  const handleApplyRecommendation = (rec: RecommendationItem) => {
    if (applyingId || completedIds.includes(rec.id)) return;
    
    setApplyingId(rec.id);
    addToast(`Applying recommendation: ${rec.title}...`, "info");

    setTimeout(() => {
      setApplyingId(null);
      setCompletedIds(prev => [...prev, rec.id]);
      
      // Update global context
      addToast(`Successfully applied: ${rec.title}`, "success");
      addNotification({
        title: "Recommendation Applied",
        message: `Successfully executed: ${rec.title}. ${rec.desc}`,
        type: "success"
      });

      // Update statistics live
      setStats(prevStats => 
        prevStats.map(stat => {
          if (stat.label === "AI Recommendations") {
            const val = parseInt(stat.value) - 1;
            return { ...stat, value: val.toString() };
          }
          if (stat.label === "Cost Estimate" && rec.savings > 0) {
            const currentVal = parseInt(stat.value.replace("$", ""));
            return { ...stat, value: `$${currentVal - rec.savings}`, change: `-$${rec.savings}` };
          }
          if (stat.label === "Security Score" && rec.id === "rec-2") {
            const currentScore = parseInt(stat.value);
            return { ...stat, value: Math.min(100, currentScore + 3).toString(), change: "+3" };
          }
          return stat;
        })
      );
    }, 1500);
  };

  const handleQuickAction = (label: string) => {
    if (runningAction) return;
    setRunningAction(label);

    if (label === "Deploy Now") {
      addToast("Initializing deployment workflow...", "info");
      setTimeout(() => {
        setRunningAction(null);
        addToast("Redirecting to active pipeline...", "success");
        router.push("/dashboard/deployments");
      }, 1000);
    } else if (label === "Security Scan") {
      addToast("Initiating cluster vulnerability scan...", "info");
      setTimeout(() => {
        setRunningAction(null);
        addToast("Security scan complete. 0 issues detected.", "success");
        addNotification({
          title: "Security Scan Completed",
          message: "Full compliance audit and vulnerability scan completed successfully. No risks identified.",
          type: "success"
        });
        setStats(prevStats => 
          prevStats.map(stat => {
            if (stat.label === "Security Score") {
              const currentScore = parseInt(stat.value);
              return { ...stat, value: Math.min(100, currentScore + 2).toString(), change: "+2" };
            }
            return stat;
          })
        );
      }, 2000);
    } else if (label === "View Logs") {
      router.push("/dashboard/logs");
    } else if (label === "Sync GitHub") {
      addToast("Syncing repositories with GitHub organization...", "info");
      setTimeout(() => {
        setRunningAction(null);
        addToast("GitHub synchronization complete. 5 repositories updated.", "success");
        addNotification({
          title: "GitHub Synchronized",
          message: "Successfully synchronized Webhooks and branch tracking with Acme organization.",
          type: "info"
        });
      }, 1500);
    }
  };

  return (
    <div className="space-y-6">
      {/* Greeting */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
        <h1 className="text-2xl font-bold text-foreground">Good morning, Vedant</h1>
        <p className="text-foreground-muted mt-1">Your infrastructure is healthy. {recs.length - completedIds.length} AI optimizations pending.</p>
      </motion.div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {stats.map((stat, i) => {
          const Icon = statIcons[stat.color] || Rocket;
          return (
            <motion.div key={stat.label} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }}
              className="glass rounded-xl p-5 hover:bg-card-hover/50 transition-colors">
              <div className="flex items-center justify-between mb-3">
                <span className="text-foreground-muted text-sm">{stat.label}</span>
                <Icon size={18} className="text-foreground-muted" />
              </div>
              <div className="flex items-end justify-between">
                <span className="text-3xl font-bold text-foreground">{stat.value}</span>
                {stat.change && (
                  <span className={`text-xs flex items-center gap-1 ${stat.trend === "up" && stat.color !== "red" ? "text-success" : stat.trend === "down" ? "text-success" : "text-danger"}`}>
                    {stat.trend === "up" ? <ArrowUpRight size={12} /> : <TrendingDown size={12} />}
                    {stat.change}
                  </span>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Traffic Chart */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="glass rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-foreground">Live Traffic</h3>
          <div className="flex gap-1">
            {timeRanges.map(t => (
              <button key={t} onClick={() => setTimeRange(t)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${timeRange === t ? "bg-primary-subtle text-primary" : "text-foreground-muted hover:text-foreground hover:bg-card"}`}>
                {t}
              </button>
            ))}
          </div>
        </div>
        <AreaChart data={trafficMetrics} color="#3b82f6" height={220} />
      </motion.div>

      {/* Recent Deployments */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="glass rounded-xl p-6">
        <h3 className="font-semibold text-foreground mb-4">Recent Deployments</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-foreground-muted border-b border-border">
              <th className="text-left py-3 font-medium">App</th>
              <th className="text-left py-3 font-medium">Environment</th>
              <th className="text-left py-3 font-medium">Status</th>
              <th className="text-left py-3 font-medium">Duration</th>
              <th className="text-left py-3 font-medium">Deployed By</th>
              <th className="text-left py-3 font-medium">Time</th>
            </tr></thead>
            <tbody>
              {deployments.map(dep => (
                <tr key={dep.id} className="border-b border-border/50 hover:bg-card-hover/30 transition-colors">
                  <td className="py-3 font-medium text-foreground">{dep.app}</td>
                  <td className="py-3"><span className={`text-xs px-2 py-0.5 rounded-full ${dep.environment === "production" ? "bg-success/10 text-success" : dep.environment === "staging" ? "bg-warning/10 text-warning" : "bg-info/10 text-info"}`}>{dep.environment}</span></td>
                  <td className="py-3"><StatusBadge status={dep.status} /></td>
                  <td className="py-3 text-foreground-muted">{dep.duration}</td>
                  <td className="py-3 text-foreground-muted">{dep.deployedBy}</td>
                  <td className="py-3 text-foreground-muted">{dep.time}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </motion.div>

      {/* AI Recommendations + Quick Actions */}
      <div className="grid md:grid-cols-2 gap-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }} className="space-y-3">
          <h3 className="font-semibold text-foreground">AI Recommendations</h3>
          {recs.map((rec) => {
            const isCompleted = completedIds.includes(rec.id);
            const isApplying = applyingId === rec.id;

            return (
              <div key={rec.id} className="glass rounded-xl p-4 flex items-center gap-4 hover:bg-card/30 transition-colors">
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <rec.icon size={18} className={rec.color} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-medium ${isCompleted ? "text-foreground-muted line-through" : "text-foreground"}`}>{rec.title}</p>
                  <p className="text-xs text-foreground-muted truncate">{rec.desc}</p>
                </div>
                <button
                  disabled={isApplying || isCompleted}
                  onClick={() => handleApplyRecommendation(rec)}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5 ${
                    isCompleted
                      ? "bg-success/10 text-success border border-success/20"
                      : isApplying
                      ? "bg-primary/20 text-primary cursor-not-allowed"
                      : "bg-primary/10 text-primary hover:bg-primary/20 cursor-pointer"
                  }`}
                >
                  {isApplying ? (
                    <>
                      <Loader2 size={12} className="animate-spin" />
                      Applying
                    </>
                  ) : isCompleted ? (
                    <>
                      <Check size={12} />
                      Applied
                    </>
                  ) : (
                    "Apply"
                  )}
                </button>
              </div>
            );
          })}
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6 }}>
          <h3 className="font-semibold text-foreground mb-3">Quick Actions</h3>
          <div className="grid grid-cols-2 gap-3">
            {[
              { icon: Rocket, label: "Deploy Now", color: "bg-primary/10 text-primary" },
              { icon: Shield, label: "Security Scan", color: "bg-success/10 text-success" },
              { icon: Terminal, label: "View Logs", color: "bg-warning/10 text-warning" },
              { icon: GitBranch, label: "Sync GitHub", color: "bg-info/10 text-info" }
            ].map(action => {
              const isRunning = runningAction === action.label;

              return (
                <button
                  key={action.label}
                  disabled={!!runningAction}
                  onClick={() => handleQuickAction(action.label)}
                  className={`glass rounded-xl p-4 flex flex-col items-center gap-2 hover:bg-card-hover/50 transition-colors disabled:opacity-50`}
                >
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${action.color}`}>
                    {isRunning ? <Loader2 size={20} className="animate-spin" /> : <action.icon size={20} />}
                  </div>
                  <span className="text-xs font-medium text-foreground">{action.label}</span>
                </button>
              );
            })}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
