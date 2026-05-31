"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { AlertTriangle, Database, DollarSign, Loader2, TrendingDown } from "lucide-react";
import { useNotifications } from "@/lib/NotificationContext";
import { LockedView } from "@/components/dashboard/LockedView";
import { api, type CostOptimization, type Project } from "@/lib/api";

export default function CostOptimizationPage() {
  const { hasDeployed } = useNotifications();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [costData, setCostData] = useState<CostOptimization | null>(null);
  const [loading, setLoading] = useState(true);
  const [costLoading, setCostLoading] = useState(false);

  useEffect(() => {
    if (!hasDeployed) return;
    async function loadProjects() {
      setLoading(true);
      try {
        const data = await api.getProjects();
        setProjects(data);
        if (data.length > 0) setSelectedProjectId(data[0].id);
      } catch {
        setProjects([]);
      } finally {
        setLoading(false);
      }
    }
    loadProjects();
  }, [hasDeployed]);

  useEffect(() => {
    if (!selectedProjectId) return;
    setCostLoading(true);
    api.getCostOptimization(selectedProjectId)
      .then(setCostData)
      .catch(() => setCostData(null))
      .finally(() => setCostLoading(false));
  }, [selectedProjectId]);

  if (!hasDeployed) {
    return (
      <div className="space-y-6">
        <LockedView featureName="Cost Optimization & FinOps" />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <p className="text-foreground-muted text-sm font-medium">Loading cost context...</p>
      </div>
    );
  }

  const recommendations = costData?.recommendations || [];
  const hasCostTelemetry = Boolean(costData && (costData.current_cost > 0 || recommendations.length > 0));

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-card border border-border rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10 border border-primary/20 text-primary">
            <Database size={20} />
          </div>
          <div>
            <h2 className="text-sm font-bold text-foreground">Cost Optimization</h2>
            <p className="text-[10px] text-foreground-muted">Uses backend cost telemetry only. No estimated savings are shown without recorded data.</p>
          </div>
        </div>

        <select
          value={selectedProjectId}
          onChange={(event) => setSelectedProjectId(event.target.value)}
          className="bg-background-secondary border border-border text-xs rounded-lg px-3 py-1.5 text-foreground focus:outline-none focus:ring-1 focus:ring-primary font-semibold max-w-[240px]"
        >
          {projects.map((project) => (
            <option key={project.id} value={project.id}>{project.full_name}</option>
          ))}
        </select>
      </div>

      {costLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 bg-card border border-border rounded-xl shadow-sm">
          <Loader2 className="w-6 h-6 animate-spin text-primary" />
          <p className="text-xs text-foreground-muted">Loading cost telemetry...</p>
        </div>
      ) : !hasCostTelemetry ? (
        <div className="bg-card border border-border rounded-xl p-10 text-center shadow-sm">
          <AlertTriangle className="w-10 h-10 mx-auto text-foreground-muted/40 mb-3" />
          <h3 className="text-sm font-bold text-foreground mb-1">No cost telemetry connected</h3>
          <p className="text-xs text-foreground-muted max-w-md mx-auto">
            Connect billing or resource-cost telemetry before showing savings, idle resource, or rightsizing recommendations.
          </p>
        </div>
      ) : (
        <>
          <div className="grid md:grid-cols-3 gap-4">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="bg-card border border-border rounded-xl p-6 text-center shadow-sm">
              <DollarSign size={32} className="text-primary mx-auto mb-2" />
              <p className="text-3xl font-bold text-foreground">${costData?.current_cost.toFixed(2)}</p>
              <p className="text-xs text-foreground-muted mt-1">Current monthly cost</p>
            </motion.div>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }} className="bg-card border border-border rounded-xl p-6 text-center shadow-sm">
              <TrendingDown size={32} className="text-success mx-auto mb-2" />
              <p className="text-3xl font-bold text-success">${costData?.savings.toFixed(2)}</p>
              <p className="text-xs text-foreground-muted mt-1">Recorded savings opportunity</p>
            </motion.div>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.16 }} className="bg-card border border-border rounded-xl p-6 text-center shadow-sm">
              <DollarSign size={32} className="text-info mx-auto mb-2" />
              <p className="text-3xl font-bold text-foreground">${costData?.recommended_cost.toFixed(2)}</p>
              <p className="text-xs text-foreground-muted mt-1">Recommended monthly cost</p>
            </motion.div>
          </div>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
            <h3 className="text-sm font-bold text-foreground">Cost Recommendations</h3>
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
              {recommendations.map((rec, index) => (
                <div key={`${rec.title}-${index}`} className="bg-card border border-border rounded-xl p-5 shadow-sm">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-[9px] uppercase px-2 py-0.5 rounded-full font-bold border bg-info/10 text-info border-info/25">backend</span>
                    <span className="text-sm font-bold text-success">${rec.savings.toFixed(2)}</span>
                  </div>
                  <h4 className="text-xs font-bold text-foreground mb-1">{rec.title}</h4>
                  <p className="text-xs text-foreground-muted leading-relaxed">{rec.description}</p>
                </div>
              ))}
            </div>
          </motion.div>
        </>
      )}
    </div>
  );
}
