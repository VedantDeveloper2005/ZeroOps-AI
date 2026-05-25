"use client";

import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { GitBranch, Brain, Box, Cloud, Shield, TrendingUp, Globe } from "lucide-react";

const steps = [
  { icon: GitBranch, label: "Connect GitHub", description: "Link your repository with one click" },
  { icon: Brain, label: "AI Analysis", description: "AI detects framework, dependencies, and architecture" },
  { icon: Box, label: "Docker Build", description: "Optimized container image built automatically" },
  { icon: Cloud, label: "Kubernetes Deploy", description: "Manifests generated, cluster deployed" },
  { icon: Shield, label: "Security Config", description: "Firewall, SSL, and policies applied" },
  { icon: TrendingUp, label: "Autoscaling", description: "Intelligent scaling rules configured" },
  { icon: Globe, label: "Live Application", description: "Your app is live and AI-managed" },
];

export function DeploymentFlowSection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.2 });

  return (
    <section ref={ref} className="py-24 px-4 relative overflow-hidden">
      <div className="max-w-3xl mx-auto">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={isInView ? { opacity: 1, y: 0 } : {}} transition={{ duration: 0.6 }} className="text-center mb-16">
          <h2 className="text-4xl md:text-5xl font-bold mb-4">
            From Code to Production <span className="gradient-text">in Seconds</span>
          </h2>
          <p className="text-foreground-muted text-lg">Seven autonomous steps. Zero manual intervention.</p>
        </motion.div>

        <div className="relative">
          {steps.map((step, i) => (
            <motion.div
              key={step.label}
              initial={{ opacity: 0, x: -30 }}
              animate={isInView ? { opacity: 1, x: 0 } : {}}
              transition={{ delay: i * 0.2, duration: 0.5 }}
              className="flex items-start gap-6 relative"
            >
              {/* Connecting line */}
              {i < steps.length - 1 && (
                <div className="absolute left-[27px] top-[56px] w-px h-12 overflow-hidden">
                  <div className="w-full h-full bg-gradient-to-b from-primary/30 to-primary/5" />
                  <motion.div
                    className="absolute top-0 w-full h-3 bg-primary rounded-full"
                    animate={{ y: ["-100%", "400%"] }}
                    transition={{ duration: 2, repeat: Infinity, delay: i * 0.3, ease: "easeInOut" }}
                    style={{ filter: "blur(1px)" }}
                  />
                </div>
              )}

              {/* Icon */}
              <motion.div
                whileHover={{ scale: 1.1 }}
                className={`w-14 h-14 rounded-2xl flex items-center justify-center flex-shrink-0 transition-all ${
                  i <= 4 ? "bg-primary/10 border border-primary/20 glow-blue" : "bg-card border border-border"
                }`}
              >
                <step.icon size={24} className={i <= 4 ? "text-primary" : "text-foreground-muted"} />
              </motion.div>

              {/* Content */}
              <div className="pb-12">
                <div className="flex items-center gap-3">
                  <span className="text-xs text-primary font-mono">STEP {String(i + 1).padStart(2, "0")}</span>
                  {i <= 4 && <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />}
                </div>
                <h3 className="text-lg font-semibold text-foreground mt-1">{step.label}</h3>
                <p className="text-sm text-foreground-muted mt-1">{step.description}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
