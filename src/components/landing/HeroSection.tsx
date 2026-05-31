"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { motion, useInView } from "framer-motion";
import { Cloud, Cpu, Rocket, ShieldCheck, Zap } from "lucide-react";

const terminalLines = [
  { text: "$ zeroops readiness --target production", type: "command" as const },
  { text: "", type: "blank" as const },
  { text: "Backend API: required for dashboard data", type: "info" as const },
  { text: "Repository analysis: fetched from authenticated backend", type: "success" as const },
  { text: "Deployments: recorded pipeline state only", type: "success" as const },
  { text: "Logs: WebSocket stream required; no synthetic fallback", type: "success" as const },
  { text: "Monitoring: database or cluster metrics required", type: "success" as const },
  { text: "Security: project-owned API status only", type: "success" as const },
  { text: "Secrets: backend secret store; Azure Key Vault when configured", type: "success" as const },
  { text: "", type: "blank" as const },
  { text: "Missing integrations render unavailable or empty states.", type: "warning" as const },
];

export function HeroSection() {
  const [visibleLines, setVisibleLines] = useState(0);
  const termRef = useRef<HTMLDivElement>(null);
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });

  useEffect(() => {
    if (!isInView) return;
    const timer = setInterval(() => {
      setVisibleLines((prev) => {
        if (prev >= terminalLines.length) {
          clearInterval(timer);
          return prev;
        }
        return prev + 1;
      });
    }, 140);
    return () => clearInterval(timer);
  }, [isInView]);

  useEffect(() => {
    if (termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight;
    }
  }, [visibleLines]);

  const lineColor = (type: string) => {
    switch (type) {
      case "command":
        return "text-white font-bold";
      case "success":
        return "text-green-400";
      case "warning":
        return "text-amber-400";
      case "error":
        return "text-red-400";
      default:
        return "text-foreground-muted";
    }
  };

  const stagger = {
    hidden: { opacity: 0, y: 30 },
    visible: (i: number) => ({
      opacity: 1,
      y: 0,
      transition: { delay: i * 0.12, duration: 0.6, ease: "easeOut" as const },
    }),
  };

  return (
    <section ref={ref} className="min-h-screen flex flex-col items-center justify-center relative overflow-hidden px-4 pt-28 pb-16">
      <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: "linear-gradient(hsl(228, 15%, 30%) 1px, transparent 1px), linear-gradient(90deg, hsl(228, 15%, 30%) 1px, transparent 1px)", backgroundSize: "60px 60px" }} />

      <div className="relative z-10 max-w-5xl mx-auto text-center">
        <motion.div custom={0} variants={stagger} initial="hidden" animate={isInView ? "visible" : "hidden"}
          className="inline-flex items-center gap-2 glass rounded-full px-4 py-1.5 mb-8 text-xs text-foreground-muted border border-border">
          <Cloud size={14} className="text-primary" />
          <span>Production-style SaaS deployment control plane</span>
          <Zap size={12} className="text-primary" />
        </motion.div>

        <motion.h1 custom={1} variants={stagger} initial="hidden" animate={isInView ? "visible" : "hidden"}
          className="text-5xl md:text-7xl font-bold tracking-tight leading-[1.1] mb-6 text-balance">
          Deploy Production-Grade Applications with{" "}
          <span className="gradient-text">AI</span>
        </motion.h1>

        <motion.p custom={2} variants={stagger} initial="hidden" animate={isInView ? "visible" : "hidden"}
          className="text-lg text-foreground-muted max-w-2xl mx-auto mb-10 leading-relaxed">
          ZeroOps connects repository analysis, authenticated deployments, logs, monitoring, secrets, and security status into one production-focused workflow.
        </motion.p>

        <motion.div custom={3} variants={stagger} initial="hidden" animate={isInView ? "visible" : "hidden"} className="flex items-center justify-center gap-4 mb-16">
          <Link href="/signup">
            <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.97 }}
              className="px-8 py-3.5 bg-primary rounded-xl text-white font-semibold text-sm glow-blue relative overflow-hidden group cursor-pointer">
              <span className="relative z-10">Start Deploying</span>
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700" />
            </motion.button>
          </Link>
          <Link href="/login">
            <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.97 }}
              className="px-8 py-3.5 glass rounded-xl font-semibold text-sm text-foreground hover:border-border-hover transition-colors cursor-pointer">
              Open Dashboard
            </motion.button>
          </Link>
        </motion.div>

        <motion.div custom={4} variants={stagger} initial="hidden" animate={isInView ? "visible" : "hidden"} className="relative max-w-3xl mx-auto">
          <div className="glass rounded-xl overflow-hidden glow-blue">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-black/20">
              <div className="w-3 h-3 rounded-full bg-red-500/80" />
              <div className="w-3 h-3 rounded-full bg-amber-500/80" />
              <div className="w-3 h-3 rounded-full bg-green-500/80" />
              <span className="text-xs text-foreground-muted ml-2 font-mono">zeroops-readiness</span>
            </div>
            <div ref={termRef} className="p-4 font-mono text-xs leading-6 h-[250px] overflow-y-auto no-scrollbar bg-black/40 text-left">
              {terminalLines.slice(0, visibleLines).map((line, i) => (
                <motion.div key={i} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}>
                  {line.type === "blank" ? <br /> : <p className={lineColor(line.type)}>{line.text}</p>}
                </motion.div>
              ))}
              {visibleLines < terminalLines.length && (
                <span className="inline-block w-2 h-4 bg-primary animate-pulse" />
              )}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-2.5 border-t border-border bg-black/35 text-[10px] font-mono text-foreground-muted">
              <span className="flex items-center gap-1.5 text-green-400 font-semibold">
                <span className="w-2 h-2 rounded-full bg-green-500" />
                REAL BACKEND DATA REQUIRED
              </span>
              <span className="flex items-center gap-1">
                <Rocket size={12} className="text-primary" />
                Recorded deployments
              </span>
              <span className="flex items-center gap-1">
                <ShieldCheck size={12} className="text-primary" />
                Authenticated APIs
              </span>
              <span className="flex items-center gap-1">
                <Cpu size={12} className="text-primary" />
                Real telemetry only
              </span>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
