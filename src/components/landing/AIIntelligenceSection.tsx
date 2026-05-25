"use client";

import { motion, useInView } from "framer-motion";
import { useRef, useState, useEffect } from "react";
import { Brain, Check, Loader, Sparkles } from "lucide-react";

const aiActions = [
  { action: "AI detected a Next.js 15 application", status: "completed" as const, time: "0.2s" },
  { action: "Scaling policy optimized automatically", status: "completed" as const, time: "0.8s" },
  { action: "Firewall rules configured for production", status: "completed" as const, time: "1.2s" },
  { action: "Security vulnerability CVE-2026-1234 patched", status: "completed" as const, time: "2.1s" },
  { action: "Traffic spike predicted for 09:00 AM", status: "active" as const, time: "Now" },
  { action: "Pre-scale web-frontend to 6 replicas", status: "predicted" as const, time: "Predicted" },
];

const aiOutput = [
  "▸ Analyzing repository structure...",
  "  Framework: Next.js 15.1.0 (TypeScript)",
  "  Dependencies: 47 packages scanned",
  "  Vulnerabilities: 3 found → auto-patching...",
  "  ✓ All vulnerabilities resolved",
  "",
  "▸ Generating deployment strategy...",
  "  Resources: 200m CPU, 256Mi Memory",
  "  Replicas: 2 (min) → 10 (max)",
  "  Scaling: AI predictive autoscaling enabled",
  "  Health: Liveness + readiness probes configured",
  "",
  "▸ Recommendation: Deploy with canary strategy",
  "  ✓ Risk Score: 23/100 (Low)",
];

export function AIIntelligenceSection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.2 });
  const [visibleOutput, setVisibleOutput] = useState(0);

  useEffect(() => {
    if (!isInView) return;
    const timer = setInterval(() => {
      setVisibleOutput(prev => { if (prev >= aiOutput.length) { clearInterval(timer); return prev; } return prev + 1; });
    }, 150);
    return () => clearInterval(timer);
  }, [isInView]);

  const statusIcon = (status: string) => {
    switch (status) {
      case "completed": return <Check size={14} className="text-success" />;
      case "active": return <Loader size={14} className="text-primary animate-spin" />;
      case "predicted": return <Sparkles size={14} className="text-accent" />;
      default: return null;
    }
  };

  const statusBg = (status: string) => {
    switch (status) {
      case "completed": return "bg-success/10 text-success";
      case "active": return "bg-primary/10 text-primary";
      case "predicted": return "bg-accent/10 text-accent";
      default: return "";
    }
  };

  return (
    <section ref={ref} className="py-24 px-4">
      <div className="max-w-7xl mx-auto">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={isInView ? { opacity: 1, y: 0 } : {}} transition={{ duration: 0.6 }} className="text-center mb-16">
          <h2 className="text-4xl md:text-5xl font-bold mb-4">
            Your Infrastructure <span className="gradient-text">Thinks for Itself</span>
          </h2>
          <p className="text-foreground-muted text-lg max-w-2xl mx-auto">
            Watch AI analyze, decide, and execute in real-time. Every action is autonomous, transparent, and reversible.
          </p>
        </motion.div>

        <div className="grid md:grid-cols-2 gap-8">
          {/* AI Timeline */}
          <div className="space-y-3">
            {aiActions.map((item, i) => (
              <motion.div key={i} initial={{ opacity: 0, x: -20 }} animate={isInView ? { opacity: 1, x: 0 } : {}} transition={{ delay: i * 0.15, duration: 0.4 }}
                className="glass rounded-xl p-4 flex items-center gap-4">
                <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <Brain size={18} className="text-primary" />
                </div>
                <div className="flex-1">
                  <p className="text-sm text-foreground">{item.action}</p>
                  <p className="text-xs text-foreground-muted mt-0.5">{item.time}</p>
                </div>
                <span className={`text-xs px-2 py-1 rounded-full font-medium flex items-center gap-1 ${statusBg(item.status)}`}>
                  {statusIcon(item.status)}
                  {item.status.charAt(0).toUpperCase() + item.status.slice(1)}
                </span>
              </motion.div>
            ))}
          </div>

          {/* AI Engine Panel */}
          <motion.div initial={{ opacity: 0, x: 20 }} animate={isInView ? { opacity: 1, x: 0 } : {}} transition={{ delay: 0.3, duration: 0.6 }} className="glass rounded-xl overflow-hidden glow-purple">
            <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
              <Brain size={18} className="text-accent" />
              <span className="text-sm font-semibold">ZeroOps AI Engine</span>
              <span className="flex items-center gap-1 ml-auto text-[10px] text-success">
                <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
                Online
              </span>
            </div>
            <div className="p-4 font-mono text-xs leading-6 h-[340px] overflow-hidden bg-black/20">
              {aiOutput.slice(0, visibleOutput).map((line, i) => (
                <motion.p key={i} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
                  className={line.includes("✓") ? "text-success" : line.includes("▸") ? "text-primary" : line.includes("Recommendation") ? "text-accent" : "text-foreground-muted"}>
                  {line || "\u00A0"}
                </motion.p>
              ))}
              {visibleOutput < aiOutput.length && <span className="inline-block w-2 h-4 bg-accent animate-pulse" />}
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
