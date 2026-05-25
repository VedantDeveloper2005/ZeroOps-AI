"use client";

import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { aiActions } from "@/lib/mock-data";
import { TrendingUp, Shield, Rocket, Heart, DollarSign, Activity, RefreshCw, Lock, ShieldCheck, Cpu, AlertTriangle, BarChart3, Maximize, CheckCircle } from "lucide-react";

const iconMap: Record<string, React.ElementType> = {
  TrendingUp, Shield, RotateCcw: RefreshCw, AlertTriangle, RefreshCw, Heart, DollarSign, Lock, Activity, Rocket, BarChart3, Cpu, ShieldCheck, Maximize, CheckCircle,
};

const typeColors: Record<string, string> = {
  scaling: "text-primary bg-primary/10",
  security: "text-danger bg-danger/10",
  deployment: "text-success bg-success/10",
  optimization: "text-accent bg-accent/10",
  healing: "text-info bg-info/10",
  monitoring: "text-warning bg-warning/10",
};

export function AutonomousShowcaseSection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.2 });
  const showcaseActions = aiActions.slice(0, 8);

  return (
    <section ref={ref} className="py-24 px-4 relative overflow-hidden">
      <div className="max-w-4xl mx-auto">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={isInView ? { opacity: 1, y: 0 } : {}} transition={{ duration: 0.6 }} className="text-center mb-16">
          <h2 className="text-4xl md:text-5xl font-bold mb-4">
            The Platform That <span className="gradient-text">Never Sleeps</span>
          </h2>
          <p className="text-foreground-muted text-lg">Watch autonomous AI actions happening across your infrastructure in real-time.</p>
        </motion.div>

        <div className="relative">
          {/* Glowing timeline line */}
          <div className="absolute left-8 top-0 bottom-0 w-px bg-gradient-to-b from-primary/30 via-accent/20 to-transparent" />

          {showcaseActions.map((action, i) => {
            const IconComp = iconMap[action.icon] || Activity;
            const colors = typeColors[action.type] || "text-foreground-muted bg-card";
            return (
              <motion.div
                key={action.id}
                initial={{ opacity: 0, y: 20 }}
                animate={isInView ? { opacity: 1, y: 0 } : {}}
                transition={{ delay: i * 0.12, duration: 0.5 }}
                className="flex items-start gap-4 mb-4 relative"
              >
                {/* Icon dot */}
                <div className={`w-16 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${colors.split(" ").slice(1).join(" ")}`}>
                  <IconComp size={18} className={colors.split(" ")[0]} />
                </div>

                {/* Content */}
                <div className="glass rounded-xl p-4 flex-1 hover:bg-card-hover/50 transition-colors">
                  <p className="text-sm text-foreground">{action.message}</p>
                  <p className="text-xs text-foreground-muted mt-1">{action.timestamp}</p>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
