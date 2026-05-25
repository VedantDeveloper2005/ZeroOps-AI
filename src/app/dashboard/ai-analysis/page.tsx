"use client";

import { motion } from "framer-motion";
import { Brain, Cpu, HardDrive, Database, Check, AlertTriangle, Rocket, ArrowRight } from "lucide-react";
import { GaugeChart } from "@/components/ui/GaugeChart";

const analysisSteps = [
  "Clone repository from GitHub",
  "Build optimized Docker image",
  "Generate Kubernetes manifests",
  "Configure ingress & networking",
  "Apply firewall rules",
  "Enable autoscaling (HPA)",
  "Setup monitoring & alerting",
  "Deploy to AKS cluster",
];

export default function AIAnalysisPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-bold">AI Analysis</h1><p className="text-foreground-muted text-sm mt-1">AI-powered repository analysis and deployment planning</p></div>
        <div className="flex gap-2">
          <button className="px-4 py-2 rounded-xl text-sm font-medium glass hover:bg-card-hover transition">Run Full Analysis</button>
          <button className="px-4 py-2 rounded-xl text-sm font-semibold bg-primary text-white glow-blue hover:bg-primary-hover transition">Deploy Now</button>
        </div>
      </div>

      {/* Framework Detection */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-xl p-6">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-xl bg-white/5 flex items-center justify-center border border-border">
            <span className="text-2xl">⚛️</span>
          </div>
          <div>
            <h3 className="font-semibold text-lg">Next.js 15.1.0 Detected</h3>
            <p className="text-sm text-foreground-muted">TypeScript • App Router • Tailwind CSS v4</p>
          </div>
          <span className="ml-auto text-xs font-medium bg-success/10 text-success px-3 py-1 rounded-full">98% Confidence</span>
        </div>
      </motion.div>

      {/* Resource Estimation + Risk Score */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[{ icon: Cpu, label: "CPU", value: "200m", rec: "Recommended" }, { icon: HardDrive, label: "Memory", value: "256Mi", rec: "Recommended" }, { icon: Database, label: "Storage", value: "1Gi", rec: "Estimated" }].map((r, i) => (
          <motion.div key={r.label} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.1 }} className="glass rounded-xl p-5 text-center">
            <r.icon size={24} className="text-primary mx-auto mb-2" />
            <p className="text-2xl font-bold text-foreground">{r.value}</p>
            <p className="text-xs text-foreground-muted">{r.label}</p>
            <span className="text-[10px] text-success mt-1 block">{r.rec}</span>
          </motion.div>
        ))}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="col-span-2 sm:col-span-1 glass rounded-xl p-5 flex flex-col items-center justify-center relative">
          <GaugeChart value={23} label="Risk Score" size={100} color="hsl(142, 76%, 45%)" />
          <span className="text-xs text-success mt-2 font-medium">Low Risk</span>
        </motion.div>
      </div>

      {/* Dependencies */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">Dependency Overview</h3>
          <div className="flex gap-2">
            <span className="text-xs px-2 py-1 rounded-full bg-primary/10 text-primary">47 packages</span>
            <span className="text-xs px-2 py-1 rounded-full bg-danger/10 text-danger flex items-center gap-1"><AlertTriangle size={12} />3 vulnerabilities</span>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {["next@15.1.0", "react@19.0.0", "framer-motion@12.0", "tailwindcss@4.0", "lucide-react@0.460", "typescript@5.7", "@prisma/client@6.0", "stripe@17.0"].map(dep => (
            <div key={dep} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-card/50 text-xs"><Check size={12} className="text-success" /><span className="text-foreground-muted font-mono">{dep}</span></div>
          ))}
        </div>
      </motion.div>

      {/* Deployment Plan */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="glass rounded-xl p-6">
        <h3 className="font-semibold mb-4 flex items-center gap-2"><Brain size={18} className="text-primary" />AI Deployment Plan</h3>
        <div className="space-y-3">
          {analysisSteps.map((step, i) => (
            <motion.div key={i} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 + i * 0.08 }}
              className="flex items-center gap-3 text-sm">
              <span className="w-7 h-7 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center flex-shrink-0">{i + 1}</span>
              <span className="text-foreground">{step}</span>
              <ArrowRight size={14} className="text-foreground-muted ml-auto" />
            </motion.div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
