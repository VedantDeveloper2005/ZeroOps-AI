"use client";

import { motion } from "framer-motion";
import {
  Rocket, GitBranch, Globe, Clock, Activity, ShieldCheck,
  Brain, ExternalLink, Copy, Plus, Sparkles, TrendingUp,
  Terminal, Settings, Key, AlertTriangle, ArrowRight, Server, CheckCircle2
} from "lucide-react";
import { useState } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { useRouter } from "next/navigation";
import { normalizeProjectId, liveUrlForProject } from "@/lib/demo-runtime";

export default function DashboardHome() {
  const { projects, isLoading: contextLoading, addToast } = useNotifications();
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState("");

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

  // Activity Feed data matching user spec
  const activities = [
    { id: 1, type: "success", title: "Deployment completed", detail: "zeroops-web-frontend deployed successfully", time: "2m ago" },
    { id: 2, type: "info", title: "Domain connected", detail: "Custom domain zeroops.app configured for web-frontend", time: "1h ago" },
    { id: 3, type: "security", title: "SSL generated", detail: "Let's Encrypt certificate configured for secure traffic", time: "3h ago" },
    { id: 4, type: "warning", title: "Traffic spike detected", detail: "Traffic increased by 240% on API services", time: "5h ago" }
  ];

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
          { label: "Applications Running", value: "12", detail: "All systems operational", color: "text-primary", icon: Server },
          { label: "Success Rate", value: "99.8%", detail: "Last 30 days build rate", color: "text-success", icon: ShieldCheck },
          { label: "Average Deploy Time", value: "42s", detail: "Fully optimized container builds", color: "text-accent", icon: Clock },
          { label: "Monthly Traffic", value: "120k", detail: "Total served requests", color: "text-info", icon: Activity }
        ].map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="bg-card border border-border rounded-2xl p-5 shadow-sm space-y-2 relative overflow-hidden group"
          >
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold text-foreground-muted uppercase tracking-wider">{stat.label}</span>
              <stat.icon size={16} className={`${stat.color} opacity-80`} />
            </div>
            <div className="space-y-1">
              <p className="text-3xl font-extrabold text-foreground tracking-tight">{stat.value}</p>
              <p className="text-[10px] text-foreground-muted font-medium">{stat.detail}</p>
            </div>
          </motion.div>
        ))}
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
                Your React apps deploy <strong className="text-foreground font-bold">20% faster</strong> than average. Node.js base cache is fully optimized.
              </p>
            </div>
            <div className="flex items-start gap-3 p-3 rounded-xl bg-card border border-border/40">
              <div className="w-5 h-5 rounded-full bg-warning/15 text-warning flex items-center justify-center shrink-0 font-bold">!</div>
              <p className="text-foreground-muted font-medium leading-relaxed">
                <strong className="text-foreground font-bold">2 applications</strong> have optimization opportunities. Enable CDN / static asset caching to reduce latency by 38%.
              </p>
            </div>
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
                // Focus/Click the AI Floating Button to open
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
            {activities.map((act) => {
              const DotColor = act.type === "success" ? "bg-success" : act.type === "warning" ? "bg-warning" : act.type === "security" ? "bg-primary" : "bg-info";

              return (
                <div key={act.id} className="flex gap-3 text-xs">
                  <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${DotColor}`} />
                  <div className="space-y-0.5 flex-1 min-w-0">
                    <p className="font-bold text-foreground">{act.title}</p>
                    <p className="text-[10px] text-foreground-muted leading-relaxed truncate">{act.detail}</p>
                    <span className="text-[9px] text-foreground-muted/60 font-mono mt-0.5 block">{act.time}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
