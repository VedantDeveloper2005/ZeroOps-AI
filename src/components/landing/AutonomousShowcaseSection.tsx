"use client";

import { useRef } from "react";
import { motion, useInView } from "framer-motion";
import { Activity, BarChart3, RefreshCw, Shield, TrendingUp } from "lucide-react";

const recordedActionTypes = [
  { title: "Deployment Events", description: "Build, deploy, rollback, and failure records from the backend pipeline.", icon: RefreshCw, color: "text-success bg-success/10" },
  { title: "Security Status", description: "Project-owned security status from authenticated API checks.", icon: Shield, color: "text-danger bg-danger/10" },
  { title: "Scaling Recommendations", description: "Pending recommendations created from recorded telemetry thresholds.", icon: TrendingUp, color: "text-primary bg-primary/10" },
  { title: "Monitoring Signals", description: "CPU, memory, error rate, and request metrics only when collected.", icon: BarChart3, color: "text-warning bg-warning/10" },
];

export function AutonomousShowcaseSection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.2 });

  return (
    <section ref={ref} className="py-24 px-4 relative overflow-hidden">
      <div className="max-w-4xl mx-auto">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={isInView ? { opacity: 1, y: 0 } : {}} transition={{ duration: 0.6 }} className="text-center mb-16">
          <h2 className="text-4xl md:text-5xl font-bold mb-4">
            Recorded Operations, <span className="gradient-text">Not Demo Noise</span>
          </h2>
          <p className="text-foreground-muted text-lg">ZeroOps surfaces actions only after the backend records them for your projects.</p>
        </motion.div>

        <div className="relative">
          <div className="absolute left-8 top-0 bottom-0 w-px bg-gradient-to-b from-primary/30 via-accent/20 to-transparent" />

          {recordedActionTypes.map((action, i) => {
            const IconComp = action.icon || Activity;
            const [textColor, bgColor] = action.color.split(" ");
            return (
              <motion.div
                key={action.title}
                initial={{ opacity: 0, y: 20 }}
                animate={isInView ? { opacity: 1, y: 0 } : {}}
                transition={{ delay: i * 0.12, duration: 0.5 }}
                className="flex items-start gap-4 mb-4 relative"
              >
                <div className={`w-16 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${bgColor}`}>
                  <IconComp size={18} className={textColor} />
                </div>

                <div className="glass rounded-xl p-4 flex-1 hover:bg-card-hover/50 transition-colors text-left">
                  <p className="text-sm font-semibold text-foreground">{action.title}</p>
                  <p className="text-xs text-foreground-muted mt-1">{action.description}</p>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
