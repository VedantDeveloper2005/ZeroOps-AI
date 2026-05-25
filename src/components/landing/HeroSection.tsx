"use client";

import { useState, useEffect, useRef } from "react";
import { motion, useInView } from "framer-motion";
import { Rocket, Cloud, Zap, Clock, Cpu } from "lucide-react";
import { terminalLines } from "@/lib/mock-data";
import Link from "next/link";

export function HeroSection() {
  const [visibleLines, setVisibleLines] = useState(0);
  const termRef = useRef<HTMLDivElement>(null);
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });

  useEffect(() => {
    if (!isInView) return;
    const maxLines = Math.min(terminalLines.length, 20);
    const timer = setInterval(() => {
      setVisibleLines(prev => {
        if (prev >= maxLines) { clearInterval(timer); return prev; }
        return prev + 1;
      });
    }, 120);
    return () => clearInterval(timer);
  }, [isInView]);

  useEffect(() => {
    if (termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight;
    }
  }, [visibleLines]);

  const lineColor = (type: string) => {
    switch (type) {
      case "command": return "text-white font-bold";
      case "success": return "text-green-400";
      case "warning": return "text-amber-400";
      case "error": return "text-red-400";
      default: return "text-foreground-muted";
    }
  };

  const stagger = { hidden: { opacity: 0, y: 30 }, visible: (i: number) => ({ opacity: 1, y: 0, transition: { delay: i * 0.12, duration: 0.6, ease: "easeOut" as const } }) };

  const floatingCards = [
    { icon: Rocket, label: "12K+", sub: "Deployments", delay: 0 },
    { icon: Clock, label: "99.99%", sub: "Uptime", delay: 0.8 },
    { icon: Cpu, label: "47ms", sub: "Avg Response", delay: 1.6 },
  ];

  return (
    <section ref={ref} className="min-h-screen flex flex-col items-center justify-center relative overflow-hidden px-4 pt-28 pb-16">
      {/* Animated gradient orbs */}
      <motion.div className="absolute w-[600px] h-[600px] rounded-full opacity-20 blur-[120px] -top-40 -left-40" style={{ background: "radial-gradient(circle, hsl(217, 91%, 60%), transparent)" }}
        animate={{ x: [0, 50, 0], y: [0, -30, 0] }} transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }} />
      <motion.div className="absolute w-[500px] h-[500px] rounded-full opacity-15 blur-[100px] top-1/3 -right-32" style={{ background: "radial-gradient(circle, hsl(265, 83%, 58%), transparent)" }}
        animate={{ x: [0, -40, 0], y: [0, 40, 0] }} transition={{ duration: 25, repeat: Infinity, ease: "easeInOut" }} />
      <motion.div className="absolute w-[400px] h-[400px] rounded-full opacity-10 blur-[100px] bottom-20 left-1/3" style={{ background: "radial-gradient(circle, hsl(199, 89%, 48%), transparent)" }}
        animate={{ x: [0, 30, 0], y: [0, -20, 0] }} transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }} />

      {/* Grid overlay */}
      <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: "linear-gradient(hsl(228, 15%, 30%) 1px, transparent 1px), linear-gradient(90deg, hsl(228, 15%, 30%) 1px, transparent 1px)", backgroundSize: "60px 60px" }} />

      <div className="relative z-10 max-w-5xl mx-auto text-center">
        {/* Badge */}
        <motion.div custom={0} variants={stagger} initial="hidden" animate={isInView ? "visible" : "hidden"}
          className="inline-flex items-center gap-2 glass rounded-full px-4 py-1.5 mb-8 text-xs text-foreground-muted border border-border">
          <Cloud size={14} className="text-primary" />
          <span>Powered by Azure Kubernetes Service</span>
          <Zap size={12} className="text-primary" />
        </motion.div>

        {/* Headline */}
        <motion.h1 custom={1} variants={stagger} initial="hidden" animate={isInView ? "visible" : "hidden"}
          className="text-5xl md:text-7xl font-bold tracking-tight leading-[1.1] mb-6 text-balance">
          Deploy Production-Grade Applications Instantly with{" "}
          <span className="gradient-text">AI</span>
        </motion.h1>

        {/* Subheadline */}
        <motion.p custom={2} variants={stagger} initial="hidden" animate={isInView ? "visible" : "hidden"}
          className="text-lg text-foreground-muted max-w-2xl mx-auto mb-10 leading-relaxed">
          ZeroOps autonomously analyzes, secures, deploys, scales, and manages your applications on Kubernetes without DevOps complexity.
        </motion.p>

        {/* CTAs */}
        <motion.div custom={3} variants={stagger} initial="hidden" animate={isInView ? "visible" : "hidden"} className="flex items-center justify-center gap-4 mb-16">
          <Link href="/signup">
            <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.97 }}
              className="px-8 py-3.5 bg-primary rounded-xl text-white font-semibold text-sm glow-blue relative overflow-hidden group cursor-pointer">
              <span className="relative z-10">Start Deploying</span>
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700" />
            </motion.button>
          </Link>
          <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.97 }}
            className="px-8 py-3.5 glass rounded-xl font-semibold text-sm text-foreground hover:border-border-hover transition-colors">
            Watch Demo
          </motion.button>
        </motion.div>

        {/* Terminal */}
        <motion.div custom={4} variants={stagger} initial="hidden" animate={isInView ? "visible" : "hidden"} className="relative max-w-3xl mx-auto">
          <div className="glass rounded-xl overflow-hidden glow-blue">
            {/* Terminal chrome */}
            <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-black/20">
              <div className="w-3 h-3 rounded-full bg-red-500/80" />
              <div className="w-3 h-3 rounded-full bg-amber-500/80" />
              <div className="w-3 h-3 rounded-full bg-green-500/80" />
              <span className="text-xs text-foreground-muted ml-2 font-mono">zeroops-terminal</span>
            </div>
            {/* Terminal content */}
            <div ref={termRef} className="p-4 font-mono text-xs leading-6 h-[250px] overflow-y-auto no-scrollbar bg-black/40">
              {terminalLines.slice(0, visibleLines).map((line, i) => (
                <motion.div key={i} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}>
                  {line.type === "blank" ? <br /> : <p className={lineColor(line.type)}>{line.text}</p>}
                </motion.div>
              ))}
              {visibleLines < 20 && (
                <span className="inline-block w-2 h-4 bg-primary animate-pulse" />
              )}
            </div>
            {/* Terminal status bar */}
            <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-2.5 border-t border-border bg-black/35 text-[10px] font-mono text-foreground-muted">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1.5 text-green-400 font-semibold">
                  <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                  AUTONOMIC FEED ACTIVE
                </span>
                <span className="hidden sm:inline border-r border-border h-3" />
                <span className="flex items-center gap-1">
                  <Rocket size={12} className="text-primary" />
                  <span>12K+ Deploys</span>
                </span>
                <span className="hidden sm:inline border-r border-border h-3" />
                <span className="flex items-center gap-1">
                  <Clock size={12} className="text-primary" />
                  <span>99.99% Uptime</span>
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1">
                  <Cpu size={12} className="text-primary" />
                  <span>47ms Response</span>
                </span>
                <span className="border-r border-border h-3" />
                <span className="bg-primary/20 text-primary px-1.5 py-0.5 rounded text-[8px] uppercase font-semibold tracking-wider">
                  AKS-EASTUS
                </span>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
