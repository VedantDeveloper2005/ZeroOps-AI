"use client";

import { motion } from "framer-motion";
import { Brain, Loader2, ShieldCheck, TrendingUp } from "lucide-react";
import { useState, useEffect, useMemo } from "react";
import { api, type Project, type HealthScore, type CostOptimization } from "@/lib/api";
import { useNotifications } from "@/lib/NotificationContext";

export default function AIAnalysisPage() {
  const { addToast, projects, isLoading: loadingProjects } = useNotifications();
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [loadingData, setLoadingData] = useState(false);
  const [healthScore, setHealthScore] = useState<HealthScore | null>(null);
  const [costOpt, setCostOpt] = useState<CostOptimization | null>(null);
  const [requestingFixId, setRequestingFixId] = useState<string | null>(null);

  useEffect(() => {
    if (projects.length > 0 && !selectedProjectId) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, selectedProjectId]);

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
    const healthRecommendations = (healthScore?.recommendations || []).map((text, index) => ({
      id: `health-${index}`,
      category: "Health",
      issue: text,
      impact: "Based on recorded deployments, metrics, and scanner output.",
      recommendation: text,
    }));

    const costRecommendations = (costOpt?.recommendations || []).map((item, index) => ({
      id: `cost-${index}`,
      category: "Cost",
      issue: item.title,
      impact: item.savings > 0 ? `Estimated savings: $${item.savings}/month.` : "Cost telemetry is still being established.",
      recommendation: item.description,
    }));

    return [...healthRecommendations, ...costRecommendations];
  }, [healthScore, costOpt]);

  const handleRequestPaidFix = async (id: string, recommendation: string) => {
    setRequestingFixId(id);
    try {
      await api.createBillingOperation({
        operation_type: "ai_code_fix",
        project_id: selectedProjectId,
        description: recommendation,
      });
      addToast("Paid fix request created. Complete payment before AI changes code.", "info");
    } catch (err) {
      console.error("Failed to create paid fix request", err);
      addToast("Could not create paid fix request.", "error");
    } finally {
      setRequestingFixId(null);
    }
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
              {card.value != null ? `${card.value}%` : "No data"}
            </p>
            <p className="text-[10px] text-foreground-muted font-medium">From recorded deployment telemetry</p>
          </motion.div>
        ))}
      </div>

      <div className="space-y-4">
        <div className="flex items-center gap-2 border-b border-border/40 pb-2">
          <ShieldCheck size={16} className="text-primary" />
          <h2 className="text-sm font-bold text-foreground uppercase tracking-wider">AI Engineering Recommendations</h2>
        </div>
        <div className="grid md:grid-cols-2 gap-6">
          {recommendations.length > 0 ? recommendations.map((rec, index) => {
            const isRequesting = requestingFixId === rec.id;
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
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-foreground">{rec.issue}</h3>
                    <p className="text-[11px] text-foreground-muted mt-1 leading-relaxed"><span className="font-bold text-foreground">Impact:</span> {rec.impact}</p>
                    <p className="text-[11px] text-foreground-muted mt-1 leading-relaxed"><span className="font-bold text-foreground font-semibold">Recommendation:</span> {rec.recommendation}</p>
                  </div>
                </div>
                <div className="pt-4 border-t border-border/20 flex justify-end">
                  <button
                    onClick={() => handleRequestPaidFix(rec.id, rec.recommendation)}
                    disabled={isRequesting}
                    className="px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 cursor-pointer bg-primary text-white hover:bg-primary-hover shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isRequesting ? (
                      <>
                        <Loader2 size={12} className="animate-spin" /> Creating request...
                      </>
                    ) : (
                      "Request Paid Fix"
                    )}
                  </button>
                </div>
              </motion.div>
            );
          }) : (
            <div className="md:col-span-2 bg-card border border-border rounded-2xl p-8 text-center">
              <p className="text-xs font-semibold text-foreground">No recommendations yet</p>
              <p className="text-[11px] text-foreground-muted mt-1">
                Deployments and telemetry must be recorded before ZeroOps can generate actionable guidance.
              </p>
            </div>
          )}
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
