"use client";

import { motion } from "framer-motion";
import {
  Rocket, GitBranch, Globe, Clock, Activity, ShieldCheck,
  Brain, Plus, Sparkles, ArrowRight, Server, Loader2, AlertTriangle
} from "lucide-react";
import { useState, useEffect } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { useRouter } from "next/navigation";
import { api, ProjectActivity, DashboardStats } from "@/lib/api";
import { normalizeProjectId, liveUrlForProject } from "@/lib/demo-runtime";

export default function DashboardHome() {
  const { projects, isLoading: contextLoading, addToast } = useNotifications();
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState("");
  
  // Real stats & activities states
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [activities, setActivities] = useState<ProjectActivity[]>([]);
  const [loadingActivities, setLoadingActivities] = useState(true);

  useEffect(() => {
    async function loadDashboardData() {
      try {
        const [statsData, activitiesData] = await Promise.allSettled([
          api.getDashboardStats(),
          api.getGlobalActivity()
        ]);
        if (statsData.status === "fulfilled") setStats(statsData.value);
        if (activitiesData.status === "fulfilled") setActivities(activitiesData.value);
      } catch (err) {
        console.error("Failed to load dashboard data", err);
      } finally {
        setLoadingActivities(false);
      }
    }
    loadDashboardData();
  }, []);

  const handleCopyUrl = (url: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(url);
    addToast("URL copied to clipboard!", "success");
  };

  const filteredProjects = projects.filter(p =>
    p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.full_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (contextLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        <p className="text-foreground-muted text-sm font-medium">Loading platform home...</p>
      </div>
    );
  }

  // Calculate success rate dynamically based on real data
  const totalDeploys = stats?.total_deployments || 0;
  const failedDeploys = stats?.failed_deployments || 0;
  const successRate = totalDeploys > 0 
    ? `${Math.round(((totalDeploys - failedDeploys) / totalDeploys) * 100)}%`
    : "100%";

  return (
    <div className="space-y-8 max-w-6xl mx-auto pb-12">
      {/* Welcome Title */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/40 pb-5">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground">Platform Overview</h1>
          <p className="text-xs text-foreground-muted">
            Manage your autonomous cloud applications and check real-time metrics.
          </p>
        </div>
      </div>

      {/* Row 1: Platform Health Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Applications Running", value: String(projects.length), detail: "All services operational", color: "text-primary", icon: Server },
          { label: "Build Success Rate", value: successRate, detail: `Based on ${totalDeploys} deployment(s)`, color: "text-success", icon: ShieldCheck },
          { label: "Failed Incidents", value: String(failedDeploys), detail: "Autonomously resolved or rolled back", color: "text-danger", icon: AlertTriangle },
          { label: "Security Compliance", value: stats ? `${stats.security_score}%` : "96%", detail: "Secrets isolated in HSM Vault", color: "text-info", icon: Activity }
        ].map((stat, i) => {
          const StatIcon = stat.icon;
          return (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="bg-card border border-border rounded-2xl p-5 shadow-sm space-y-2 relative overflow-hidden group"
            >
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold text-foreground-muted uppercase tracking-wider">{stat.label}</span>
                <StatIcon size={16} className={`${stat.color} opacity-80`} />
              </div>
              <div className="space-y-1">
                <p className="text-3xl font-extrabold text-foreground tracking-tight">{stat.value}</p>
                <p className="text-[10px] text-foreground-muted font-medium">{stat.detail}</p>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Row 2: AI Insights & Quick Actions */}
      <div className="grid md:grid-cols-3 gap-6">
        {/* AI Insights Card */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          className="md:col-span-2 glass rounded-2xl border border-primary/20 bg-gradient-to-r from-primary/5 via-accent/5 to-transparent p-6 shadow-sm space-y-4"
        >
          <div className="flex items-center gap-2">
            <Sparkles className="text-primary w-5 h-5 animate-pulse" />
            <h3 className="text-sm font-bold text-foreground uppercase tracking-wider">AI Platform Insights</h3>
          </div>
          <div className="space-y-3.5 text-xs">
            <div className="flex items-start gap-3 p-3 rounded-xl bg-card border border-border/40">
              <div className="w-5 h-5 rounded-full bg-success/15 text-success flex items-center justify-center shrink-0 font-bold">✓</div>
              <p className="text-foreground-muted font-medium leading-relaxed">
                ZeroOps AI is actively monitoring your deployed applications. Build pipelines and base image caches are fully optimized.
              </p>
            </div>
            {projects.length > 0 ? (
              <div className="flex items-start gap-3 p-3 rounded-xl bg-card border border-border/40">
                <div className="w-5 h-5 rounded-full bg-warning/15 text-warning flex items-center justify-center shrink-0 font-bold">!</div>
                <p className="text-foreground-muted font-medium leading-relaxed">
                  Autonomic cost scaling opportunities detected. Navigate to <strong className="text-foreground font-bold hover:underline cursor-pointer" onClick={() => router.push("/dashboard/ai-analysis")}>AI Insights</strong> to audit instance tiers and save up to $8/month.
                </p>
              </div>
            ) : (
              <div className="flex items-start gap-3 p-3 rounded-xl bg-card border border-border/40">
                <div className="w-5 h-5 rounded-full bg-info/15 text-info flex items-center justify-center shrink-0 font-bold">i</div>
                <p className="text-foreground-muted font-medium leading-relaxed">
                  No active projects detected. Import your first codebase from GitHub to activate zero-config container deployments.
                </p>
              </div>
            )}
          </div>
        </motion.div>

        {/* Quick Actions Card */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-card border border-border rounded-2xl p-6 shadow-sm flex flex-col justify-between"
        >
          <h3 className="text-xs font-bold text-foreground uppercase tracking-wider mb-4 flex items-center gap-1.5">
            <Activity size={14} className="text-primary" /> Quick Actions
          </h3>
          <div className="grid grid-cols-1 gap-2 flex-1">
            <button
              onClick={() => router.push("/dashboard/repositories")}
              className="flex items-center justify-between p-2.5 rounded-xl border border-border/80 hover:border-primary/40 hover:bg-card-hover/40 text-left transition text-xs font-semibold text-foreground cursor-pointer"
            >
              <span className="flex items-center gap-2">
                <Plus size={14} className="text-primary" /> Deploy New App
              </span>
              <ArrowRight size={12} className="text-foreground-muted" />
            </button>
            <button
              onClick={() => router.push("/dashboard/repositories")}
              className="flex items-center justify-between p-2.5 rounded-xl border border-border/80 hover:border-primary/40 hover:bg-card-hover/40 text-left transition text-xs font-semibold text-foreground cursor-pointer"
            >
              <span className="flex items-center gap-2">
                <GitBranch size={14} className="text-accent" /> Import GitHub Repo
              </span>
              <ArrowRight size={12} className="text-foreground-muted" />
            </button>
            <button
              onClick={() => router.push("/dashboard/settings")}
              className="flex items-center justify-between p-2.5 rounded-xl border border-border/80 hover:border-primary/40 hover:bg-card-hover/40 text-left transition text-xs font-semibold text-foreground cursor-pointer"
            >
              <span className="flex items-center gap-2">
                <Globe size={14} className="text-success" /> Connect Domain
              </span>
              <ArrowRight size={12} className="text-foreground-muted" />
            </button>
            <button
              onClick={() => {
                const aiBtn = document.querySelector(".fixed.bottom-6.right-6 button") as HTMLButtonElement;
                if (aiBtn) aiBtn.click();
              }}
              className="flex items-center justify-between p-2.5 bg-primary/10 border border-primary/20 hover:bg-primary/15 rounded-xl text-left transition text-xs font-semibold text-primary cursor-pointer"
            >
              <span className="flex items-center gap-2">
                <Brain size={14} /> Ask ZeroOps AI
              </span>
              <ArrowRight size={12} />
            </button>
          </div>
        </motion.div>
      </div>

      {/* Main Apps Grid & Activity Feed Row */}
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Connected Applications List */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-2">
            <h2 className="text-sm font-bold text-foreground uppercase tracking-wider flex items-center gap-1.5">
              <Server size={14} className="text-primary" /> Active Applications
            </h2>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter apps..."
              className="bg-card border border-border rounded-lg px-2.5 py-1 text-xs text-foreground focus:border-primary focus:outline-none placeholder:text-foreground-muted max-w-[200px]"
            />
          </div>

          {filteredProjects.length === 0 ? (
            <div className="text-center py-12 bg-card border border-border rounded-2xl space-y-4">
              <Rocket size={32} className="text-foreground-muted/30 mx-auto" />
              <div className="space-y-1">
                <p className="text-sm font-bold text-foreground">No applications deployed yet</p>
                <p className="text-xs text-foreground-muted">Deploy your first application in under 60 seconds.</p>
              </div>
              <button
                onClick={() => router.push("/dashboard/repositories")}
                className="px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-bold rounded-xl transition cursor-pointer shadow-md shadow-primary/10"
              >
                Deploy Application
              </button>
            </div>
          ) : (
            <div className="grid gap-3">
              {filteredProjects.map((proj) => {
                const prId = normalizeProjectId(proj.full_name);
                const appUrl = liveUrlForProject(prId);
                const isHealthy = proj.status === "active" || proj.latest_deployment_status === "running";

                return (
                  <motion.div
                    key={proj.id}
                    onClick={() => router.push(`/dashboard/apps/${proj.id}`)}
                    whileHover={{ y: -2 }}
                    className="p-4 rounded-xl border border-border bg-card hover:bg-card-hover/40 transition cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm"
                  >
                    <div className="space-y-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-extrabold text-sm text-foreground truncate">{proj.name}</span>
                        <span className="text-[10px] px-2 py-0.2 rounded bg-background-secondary border border-border font-semibold text-foreground-muted">
                          {proj.framework}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-foreground-muted">
                        <span className="flex items-center gap-1">
                          <Globe size={11} className="text-primary" />
                          <a
                            href={appUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => handleCopyUrl(appUrl, e)}
                            className="font-mono text-[11px] hover:text-primary transition hover:underline truncate max-w-[180px]"
                          >
                            {appUrl.replace("https://", "")}
                          </a>
                        </span>
                        <span className="flex items-center gap-1 font-mono text-[10px]">
                          <GitBranch size={10} /> {proj.branch}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-3 shrink-0 self-end sm:self-auto">
                      <div className="flex items-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full ${isHealthy ? "bg-success animate-pulse" : "bg-warning animate-pulse"}`} />
                        <span className="text-[10px] font-bold uppercase tracking-wider text-foreground-muted">
                          {isHealthy ? "Healthy & Live" : "Idle"}
                        </span>
                      </div>
                      <ArrowRight size={14} className="text-foreground-muted group-hover:text-primary transition-all" />
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}
        </div>

        {/* Platform Activity Feed */}
        <div className="space-y-4">
          <div className="border-b border-border/40 pb-2">
            <h2 className="text-sm font-bold text-foreground uppercase tracking-wider flex items-center gap-1.5">
              <Clock size={14} className="text-primary" /> Live Activity Feed
            </h2>
          </div>

          <div className="bg-card border border-border rounded-2xl p-4.5 space-y-4 shadow-sm">
            {loadingActivities ? (
              <div className="flex items-center gap-2 text-foreground-muted font-medium py-4 text-xs justify-center">
                <Loader2 size={14} className="animate-spin text-primary" /> Loading live operations logs...
              </div>
            ) : activities.length > 0 ? (
              <div className="space-y-4">
                {activities.slice(0, 5).map((act) => {
                  const actDate = new Date(act.created_at);
                  const dateStr = actDate.toLocaleDateString("en-US", { month: "short", day: "numeric" });
                  const timeStr = actDate.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });

                  const isHealed = act.action.toLowerCase().includes("healing") || act.action.toLowerCase().includes("rollback") || act.action.toLowerCase().includes("mitigated");
                  const isFailure = act.action.toLowerCase().includes("failed") || act.action.toLowerCase().includes("error") || act.action.toLowerCase().includes("critical");
                  const isDomain = act.action.toLowerCase().includes("domain");
                  
                  const dotColor = isFailure 
                    ? "bg-danger" 
                    : isHealed 
                    ? "bg-warning" 
                    : isDomain 
                    ? "bg-primary" 
                    : "bg-success";

                  return (
                    <div key={act.id} className="flex gap-3 text-xs leading-normal">
                      <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${dotColor}`} />
                      <div className="space-y-0.5 flex-1 min-w-0">
                        <p className="font-bold text-foreground leading-snug">{act.action}</p>
                        <p className="text-[10px] text-foreground-muted leading-relaxed truncate">{act.details}</p>
                        <span className="text-[9px] text-foreground-muted/60 font-mono mt-0.5 block">{act.project_name} • {dateStr} at {timeStr}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-xs text-foreground-muted py-6 font-medium text-center">
                No activity logs available.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
