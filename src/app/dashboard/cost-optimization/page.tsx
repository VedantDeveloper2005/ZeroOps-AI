"use client";

import { motion } from "framer-motion";
import { DollarSign, TrendingDown, AlertTriangle } from "lucide-react";
interface MetricPoint {
  time: string;
  value: number;
}

function generateMetricData(points: number, min: number, max: number, trend: "up" | "down" | "stable" = "stable"): MetricPoint[] {
  const data: MetricPoint[] = [];
  let current = (min + max) / 2;
  const pseudoRandom = (seed: number) => {
    const x = Math.sin(seed) * 10000;
    return x - Math.floor(x);
  };
  for (let i = 0; i < points; i++) {
    const seed = i + min + max + (trend === "up" ? 1 : trend === "down" ? 2 : 3);
    const noise = (pseudoRandom(seed) - 0.5) * (max - min) * 0.3;
    const trendBias = trend === "up" ? 0.5 : trend === "down" ? -0.5 : 0;
    current = Math.max(min, Math.min(max, current + noise + trendBias));
    const hour = Math.floor(i / (points / 24));
    data.push({
      time: `${String(hour).padStart(2, "0")}:${String((i * 60 / points * 24) % 60 | 0).padStart(2, "0")}`,
      value: Math.round(current * 10) / 10,
    });
  }
  return data;
}

interface CostRecommendation {
  id: string;
  title: string;
  description: string;
  savings: string;
  type: "rightsize" | "idle" | "reserved" | "spot" | "consolidate";
  impact: "high" | "medium" | "low";
}

const costRecommendations: CostRecommendation[] = [
  { id: "cost-001", title: "Right-size api-gateway", description: "Reduce CPU limit 500m→200m based on 30-day usage analysis", savings: "$18/mo", type: "rightsize", impact: "medium" },
  { id: "cost-002", title: "Enable Spot Instances for Staging", description: "Switch staging cluster nodes to spot instances for non-critical workloads", savings: "$45/mo", type: "spot", impact: "high" },
  { id: "cost-003", title: "Consolidate Idle Staging Pods", description: "3 pods in staging haven't received traffic in 72 hours", savings: "$22/mo", type: "idle", impact: "medium" },
  { id: "cost-004", title: "Reserved Pricing for Production", description: "Switch to 1-year reserved instances for stable production workloads", savings: "$42/mo", type: "reserved", impact: "high" },
  { id: "cost-005", title: "Optimize Container Images", description: "Multi-stage builds could reduce image sizes by 60%, saving on registry storage", savings: "$8/mo", type: "consolidate", impact: "low" },
];

const idleResources = [
  { name: "staging-api", type: "Pod", lastActive: "72h ago", allocatedCpu: "500m", allocatedMemory: "512Mi", suggestedAction: "Scale to 0" },
  { name: "test-worker-2", type: "Pod", lastActive: "48h ago", allocatedCpu: "250m", allocatedMemory: "256Mi", suggestedAction: "Scale to 0" },
  { name: "dev-cache", type: "Pod", lastActive: "5 days ago", allocatedCpu: "100m", allocatedMemory: "128Mi", suggestedAction: "Delete" },
];

const overprovisionedPods = [
  { pod: "api-gateway", allocatedCpu: "500m", usedCpu: "89m", allocatedMemory: "512Mi", usedMemory: "156Mi", savings: "$12/mo" },
  { pod: "ml-pipeline", allocatedCpu: "1000m", usedCpu: "234m", allocatedMemory: "2Gi", usedMemory: "890Mi", savings: "$28/mo" },
  { pod: "notification-svc", allocatedCpu: "250m", usedCpu: "45m", allocatedMemory: "256Mi", usedMemory: "67Mi", savings: "$6/mo" },
];
import { GaugeChart } from "@/components/ui/GaugeChart";
import { AreaChart } from "@/components/ui/AreaChart";
import { useNotifications } from "@/lib/NotificationContext";
import { LockedView } from "@/components/dashboard/LockedView";

const costTrend = generateMetricData(30, 8, 16, "down");
const costBreakdown = [
  { label: "Compute", value: 60, color: "bg-primary" },
  { label: "Storage", value: 20, color: "bg-accent" },
  { label: "Network", value: 15, color: "bg-info" },
  { label: "Egress", value: 5, color: "bg-warning" },
];
const impactColor: Record<string, string> = { high: "bg-danger/10 text-danger", medium: "bg-warning/10 text-warning", low: "bg-info/10 text-info" };

export default function CostOptimizationPage() {
  const { hasDeployed } = useNotifications();

  if (!hasDeployed) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Cost Optimization</h1>
          <p className="text-foreground-muted text-sm mt-1">AI-powered FinOps and resource efficiency analysis</p>
        </div>
        <LockedView featureName="Cost Optimization & FinOps" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-bold">Cost Optimization</h1><p className="text-foreground-muted text-sm mt-1">AI-powered FinOps and resource efficiency analysis</p></div>

      {/* Score + Savings + Breakdown */}
      <div className="grid md:grid-cols-3 gap-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-xl p-6 flex flex-col items-center justify-center relative">
          <GaugeChart value={78} label="Efficiency Score" size={130} color="#3b82f6" />
          <span className="text-xs text-primary mt-2 font-medium">Good</span>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass rounded-xl p-6 text-center glow-green">
          <DollarSign size={32} className="text-success mx-auto mb-2" />
          <p className="text-4xl font-bold text-success">$127</p>
          <p className="text-sm text-foreground-muted">Monthly Savings Potential</p>
          <p className="text-xs text-foreground-muted mt-1">5 optimizations available</p>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass rounded-xl p-6">
          <h3 className="font-semibold mb-4">Cost Breakdown</h3>
          <div className="space-y-3">
            {costBreakdown.map(item => (
              <div key={item.label}>
                <div className="flex justify-between text-sm mb-1"><span className="text-foreground-muted">{item.label}</span><span className="text-foreground">{item.value}%</span></div>
                <div className="h-2 bg-card rounded-full overflow-hidden">
                  <motion.div initial={{ width: 0 }} animate={{ width: `${item.value}%` }} transition={{ duration: 1 }} className={`h-full rounded-full ${item.color}`} />
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Cost Trend */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass rounded-xl p-6">
        <h3 className="font-semibold mb-4">Daily Cost Trend (30 days)</h3>
        <AreaChart data={costTrend} color="#22c55e" height={180} />
      </motion.div>

      {/* Recommendations */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
        <h3 className="font-semibold mb-4">AI Cost Recommendations</h3>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {costRecommendations.map((rec, i) => (
            <motion.div key={rec.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 + i * 0.08 }}
              className="glass rounded-xl p-5">
              <div className="flex items-center justify-between mb-3">
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${impactColor[rec.impact]}`}>{rec.impact} impact</span>
                <span className="text-sm font-bold text-success">{rec.savings}</span>
              </div>
              <h4 className="text-sm font-semibold text-foreground mb-1">{rec.title}</h4>
              <p className="text-xs text-foreground-muted mb-3">{rec.description}</p>
              <button className="w-full py-2 bg-primary/10 text-primary rounded-lg text-xs font-medium hover:bg-primary/20 transition">Apply Optimization</button>
            </motion.div>
          ))}
        </div>
      </motion.div>

      {/* Idle Resources + Overprovisioned */}
      <div className="grid md:grid-cols-2 gap-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="glass rounded-xl p-6">
          <h3 className="font-semibold mb-4 flex items-center gap-2"><AlertTriangle size={16} className="text-warning" />Idle Resources</h3>
          <div className="space-y-3">
            {idleResources.map(r => (
              <div key={r.name} className="flex items-center justify-between p-3 rounded-lg bg-card/50">
                <div><p className="text-sm font-medium text-foreground">{r.name}</p><p className="text-xs text-foreground-muted">{r.type} • Last active: {r.lastActive}</p></div>
                <button className="text-xs bg-warning/10 text-warning px-3 py-1 rounded-lg font-medium">{r.suggestedAction}</button>
              </div>
            ))}
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }} className="glass rounded-xl p-6">
          <h3 className="font-semibold mb-4 flex items-center gap-2"><TrendingDown size={16} className="text-info" />Overprovisioned Pods</h3>
          <table className="w-full text-xs">
            <thead><tr className="text-foreground-muted border-b border-border"><th className="text-left py-2">Pod</th><th className="text-left py-2">CPU</th><th className="text-left py-2">Memory</th><th className="text-left py-2">Savings</th></tr></thead>
            <tbody>{overprovisionedPods.map(p => (
              <tr key={p.pod} className="border-b border-border/50">
                <td className="py-2 font-medium text-foreground">{p.pod}</td>
                <td className="py-2 text-foreground-muted">{p.usedCpu}/{p.allocatedCpu}</td>
                <td className="py-2 text-foreground-muted">{p.usedMemory}/{p.allocatedMemory}</td>
                <td className="py-2 text-success font-medium">{p.savings}</td>
              </tr>
            ))}</tbody>
          </table>
        </motion.div>
      </div>
    </div>
  );
}
