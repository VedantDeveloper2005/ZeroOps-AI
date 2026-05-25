"use client";

import { motion } from "framer-motion";
import { LayoutDashboard, TrendingUp, TrendingDown, ArrowUpRight, Rocket, Shield, Terminal, GitBranch, Brain, Cpu, Zap, Loader2, Check } from "lucide-react";
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
  const { addToast, addNotification } = useNotifications();
  const [timeRange, setTimeRange] = useState("24h");
  const [stats, setStats] = useState(initialStats);
  const [recs, setRecs] = useState<RecommendationItem[]>([
    { id: "rec-1", icon: TrendingUp, title: "Optimize api-gateway scaling", desc: "Reduce CPU allocation 500m→200m", color: "text-primary", savings: 18 },
    { id: "rec-2", icon: Shield, title: "Patch CVE-2026-1234", desc: "Critical vulnerability in base image", color: "text-danger", savings: 0 },
    { id: "rec-3", icon: Cpu, title: "Reduce staging costs", desc: "3 idle pods detected — save $22/mo", color: "text-warning", savings: 22 },
  ]);

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
