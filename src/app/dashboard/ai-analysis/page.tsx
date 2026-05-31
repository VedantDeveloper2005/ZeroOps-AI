"use client";

import { motion } from "framer-motion";
import { Brain, Loader2, ShieldCheck, TrendingUp } from "lucide-react";
import { useState, useEffect, useMemo } from "react";
import { api, type Project, type HealthScore, type CostOptimization } from "@/lib/api";

export default function AIAnalysisPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [loadingData, setLoadingData] = useState(false);
  const [healthScore, setHealthScore] = useState<HealthScore | null>(null);
  const [costOpt, setCostOpt] = useState<CostOptimization | null>(null);

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

  const recommendations = useMemo(() => {
    const items: { title: string; description: string }[] = [];
    if (healthScore?.recommendations?.length) {
      items.push(
        ...healthScore.recommendations.map((text) => ({
          title: text,
          description: "AI identified this as an actionable improvement.",
        }))
      );
    }
    if (costOpt?.recommendations?.length) {
      items.push(
        ...costOpt.recommendations.map((rec) => ({
          title: rec.title,
          description: rec.description,
        }))
      );
    }
    if (items.length > 0) return items;
    return [
      { title: "Reduce bundle size", description: "Audit large dependencies and split vendor chunks." },
      { title: "Optimize images", description: "Use responsive formats and lazy loading." },
      { title: "Enable caching", description: "Cache static assets and API responses." },
      { title: "Remove unused packages", description: "Trim unused dependencies to speed builds." },
      { title: "Improve startup performance", description: "Defer heavy initialization work." },
    ];
  }, [healthScore, costOpt]);

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
              {card.value != null ? `${card.value}%` : "—"}
            </p>
            <p className="text-[10px] text-foreground-muted">Updated from latest deployment data</p>
          </motion.div>
        ))}
      </div>

      <div className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center gap-2">
          <ShieldCheck size={16} className="text-primary" />
          <h2 className="text-sm font-bold text-foreground">AI Recommendations</h2>
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          {recommendations.map((rec, index) => (
            <motion.div
              key={`${rec.title}-${index}`}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.04 }}
              className="border border-border rounded-xl p-4 bg-background-secondary/40"
            >
              <p className="text-xs font-bold text-foreground">{rec.title}</p>
              <p className="text-[11px] text-foreground-muted mt-1">{rec.description}</p>
            </motion.div>
          ))}
        </div>
      </div>

      <div className="bg-background-secondary border border-border rounded-2xl p-5 flex items-center gap-3">
        <TrendingUp size={18} className="text-primary" />
        <div>
          <p className="text-xs font-semibold text-foreground">Need deeper analysis?</p>
          <p className="text-[11px] text-foreground-muted">Use the ZeroOps AI assistant to audit a specific deployment or service.</p>
        </div>
      </div>
    </div>
  );
}
