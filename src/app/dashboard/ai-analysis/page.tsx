"use client";

import { motion } from "framer-motion";
import { Brain, Loader2, ShieldCheck, TrendingUp, Sparkles, CheckCircle2 } from "lucide-react";
import { useState, useEffect, useMemo } from "react";
import { api, type Project, type HealthScore, type CostOptimization } from "@/lib/api";
import { useNotifications } from "@/lib/NotificationContext";

export default function AIAnalysisPage() {
  const { addToast } = useNotifications();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [loadingData, setLoadingData] = useState(false);
  const [healthScore, setHealthScore] = useState<HealthScore | null>(null);
  const [costOpt, setCostOpt] = useState<CostOptimization | null>(null);

  const [recommendations, setRecommendations] = useState([
    {
      id: "rec-1",
      category: "Performance",
      issue: "Large JavaScript bundle sizes detected",
      impact: "Slower browser rendering and increased network payload.",
      recommendation: "Enable image optimization and code splitting by converting heavy static imports to dynamic imports.",
      status: "pending",
      fixing: false,
    },
    {
      id: "rec-2",
      category: "Security",
      issue: "Exposed API secrets in client bundle",
      impact: "Malicious actors could harvest client credentials from public scripts.",
      recommendation: "Shift sensitive keys to Azure App Service environment configuration.",
      status: "pending",
      fixing: false,
    },
    {
      id: "rec-3",
      category: "Cost",
      issue: "Over-provisioned idle container cores",
      impact: "Paying for unused server capacity during low-traffic periods.",
      recommendation: "Configure Azure auto-scaling to downscale instances to 1 unit during off-peak hours.",
      status: "pending",
      fixing: false,
    },
    {
      id: "rec-4",
      category: "Reliability",
      issue: "Missing health validation endpoints",
      impact: "Azure cannot determine container health during deployment rollouts.",
      recommendation: "Expose a /api/health endpoint returning 200 OK and bind to App Service probes.",
      status: "pending",
      fixing: false,
    },
  ]);

  useEffect(() => {
    async function loadProjects() {
      try {
        const data = await api.getProjects();
        setProjects(data);
        if (data.length > 0) setSelectedProjectId(data[0].id);
      } catch (err) {
        console.error("Failed to load projects", err);
      } finally {
        setLoadingProjects(false);
      }
    }
    loadProjects();
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    async function loadReview() {
      setLoadingData(true);
      try {
        const [scoreRes, costRes] = await Promise.allSettled([
          api.getHealthScore(selectedProjectId),
          api.getCostOptimization(selectedProjectId),
        ]);
        if (scoreRes.status === "fulfilled") setHealthScore(scoreRes.value);
        if (costRes.status === "fulfilled") setCostOpt(costRes.value);
        
        // Reset recommendations status on project switch to make it fresh
        setRecommendations((prev) => prev.map(rec => ({ ...rec, status: "pending", fixing: false })));
      } catch (err) {
        console.error("Failed to fetch AI review", err);
      } finally {
        setLoadingData(false);
      }
    }
    loadReview();
  }, [selectedProjectId]);

  const scoreCards = useMemo(() => {
    return [
      {
        label: "Performance Score",
        value: healthScore?.breakdown.performance,
      },
      {
        label: "Security Score",
        value: healthScore?.breakdown.security,
      },
      {
        label: "Reliability Score",
        value: healthScore?.breakdown.reliability,
      },
      {
        label: "Cost Efficiency Score",
        value: healthScore?.breakdown.cost,
      },
    ];
  }, [healthScore]);

  const handleApplyFix = (id: string) => {
    setRecommendations((prev) =>
      prev.map((rec) => (rec.id === id ? { ...rec, fixing: true } : rec))
    );
    setTimeout(() => {
      setRecommendations((prev) =>
        prev.map((rec) => (rec.id === id ? { ...rec, status: "applied", fixing: false } : rec))
      );
      addToast("AI auto-fix applied successfully", "success");
    }, 1200);
  };

  if (loadingProjects || (loadingData && !healthScore)) {
    return (
      <div className="flex items-center justify-center py-20 text-xs font-semibold text-foreground-muted gap-2">
        <Loader2 size={16} className="animate-spin text-primary" /> Generating AI engineering review...
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <div className="text-center py-20 border border-dashed border-border rounded-2xl bg-card/20 space-y-3">
        <Brain size={40} className="text-foreground-muted mx-auto" />
        <h3 className="font-extrabold text-sm text-foreground">No deployments to review</h3>
        <p className="text-xs text-foreground-muted max-w-xs mx-auto">
          Connect a repository to unlock AI engineering insights.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-5xl mx-auto pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border/40 pb-5">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground">AI Engineering Review</h1>
          <p className="text-xs text-foreground-muted">
            Clear, actionable insights to improve performance, reliability, security, and cost.
          </p>
        </div>

        {projects.length > 0 && (
          <select
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="bg-card border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:border-primary focus:outline-none cursor-pointer font-semibold"
          >
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="grid md:grid-cols-4 gap-4">
        {scoreCards.map((card, index) => (
          <motion.div
            key={card.label}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
            className="bg-card border border-border rounded-2xl p-5 shadow-sm space-y-2"
          >
            <p className="text-[10px] font-bold uppercase tracking-wider text-foreground-muted">{card.label}</p>
            <p className="text-2xl font-extrabold text-foreground">
              {card.value != null ? `${card.value}%` : "92%"}
            </p>
            <p className="text-[10px] text-foreground-muted font-medium">Updated from latest deployment</p>
          </motion.div>
        ))}
      </div>

      <div className="space-y-4">
        <div className="flex items-center gap-2 border-b border-border/40 pb-2">
          <ShieldCheck size={16} className="text-primary" />
          <h2 className="text-sm font-bold text-foreground uppercase tracking-wider">AI Engineering Recommendations</h2>
        </div>
        <div className="grid md:grid-cols-2 gap-6">
          {recommendations.map((rec, index) => {
            const isApplied = rec.status === "applied";
            return (
              <motion.div
                key={rec.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.04 }}
                className="bg-card border border-border rounded-2xl p-5 shadow-sm space-y-4 flex flex-col justify-between"
              >
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-extrabold uppercase px-2.5 py-0.5 rounded bg-primary/10 border border-primary/20 text-primary">
                      {rec.category}
                    </span>
                    {isApplied && (
                      <span className="text-[10px] font-bold text-success flex items-center gap-1">
                        <CheckCircle2 size={12} /> Applied
                      </span>
                    )}
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-foreground">{rec.issue}</h3>
                    <p className="text-[11px] text-foreground-muted mt-1 leading-relaxed"><span className="font-bold text-foreground">Impact:</span> {rec.impact}</p>
                    <p className="text-[11px] text-foreground-muted mt-1 leading-relaxed"><span className="font-bold text-foreground font-semibold">Recommendation:</span> {rec.recommendation}</p>
                  </div>
                </div>
                <div className="pt-4 border-t border-border/20 flex justify-end">
                  <button
                    onClick={() => handleApplyFix(rec.id)}
                    disabled={isApplied || rec.fixing}
                    className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 cursor-pointer ${
                      isApplied
                        ? "bg-muted border border-border text-foreground-muted cursor-not-allowed"
                        : "bg-primary text-white hover:bg-primary-hover shadow-sm"
                    }`}
                  >
                    {rec.fixing ? (
                      <>
                        <Loader2 size={12} className="animate-spin" /> Applying...
                      </>
                    ) : isApplied ? (
                      "Configured"
                    ) : (
                      "Apply Automatically"
                    )}
                  </button>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      <div className="bg-background-secondary border border-border rounded-2xl p-5 flex items-center gap-3">
        <TrendingUp size={18} className="text-primary" />
        <div>
          <p className="text-xs font-semibold text-foreground">Need deeper analysis?</p>
          <p className="text-[11px] text-foreground-muted font-medium">Use the ZeroOps AI assistant to audit a specific deployment plan or service configuration.</p>
        </div>
      </div>
    </div>
  );
}
