"use client";

import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { Shield, Check } from "lucide-react";

const securityFeatures = [
  "Firewall Automation",
  "HTTPS Everywhere",
  "Vulnerability Scanning",
  "Deployment Isolation",
  "Secret Management",
  "AI Threat Detection",
];

export function SecuritySection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.3 });

  return (
    <section ref={ref} className="py-24 px-4 relative overflow-hidden">
      {/* Cyber grid background */}
      <div className="absolute inset-0 opacity-[0.02]" style={{ backgroundImage: "linear-gradient(hsl(217, 91%, 60%) 1px, transparent 1px), linear-gradient(90deg, hsl(217, 91%, 60%) 1px, transparent 1px)", backgroundSize: "40px 40px" }} />

      <div className="max-w-7xl mx-auto grid md:grid-cols-5 gap-12 items-center">
        {/* Left content (3/5) */}
        <motion.div initial={{ opacity: 0, x: -30 }} animate={isInView ? { opacity: 1, x: 0 } : {}} transition={{ duration: 0.6 }} className="md:col-span-3">
          <h2 className="text-4xl md:text-5xl font-bold mb-6">
            Enterprise-Grade Security,{" "}
            <span className="gradient-text">Automated by AI</span>
          </h2>
          <p className="text-foreground-muted text-lg mb-8 leading-relaxed">
            ZeroOps applies defense-in-depth security automatically. Every deployment is isolated, encrypted, scanned, and monitored by AI in real time.
          </p>
          <div className="grid grid-cols-2 gap-4">
            {securityFeatures.map((feature, i) => (
              <motion.div
                key={feature}
                initial={{ opacity: 0, y: 10 }}
                animate={isInView ? { opacity: 1, y: 0 } : {}}
                transition={{ delay: 0.3 + i * 0.1, duration: 0.4 }}
                className="flex items-center gap-3"
              >
                <div className="w-6 h-6 rounded-full bg-success/10 flex items-center justify-center flex-shrink-0">
                  <Check size={14} className="text-success" />
                </div>
                <span className="text-sm text-foreground font-medium">{feature}</span>
              </motion.div>
            ))}
          </div>
        </motion.div>

        {/* Right visual (2/5) */}
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={isInView ? { opacity: 1, scale: 1 } : {}}
          transition={{ duration: 0.8, delay: 0.2 }}
          className="md:col-span-2 flex items-center justify-center"
        >
          <div className="relative w-64 h-64">
            {/* Concentric glow rings */}
            {[1, 2, 3].map(i => (
              <motion.div key={i}
                className="absolute inset-0 rounded-full border border-primary/10"
                style={{ inset: `${-i * 20}px` }}
                animate={{ scale: [1, 1.05, 1], opacity: [0.3, 0.5, 0.3] }}
                transition={{ duration: 3, repeat: Infinity, delay: i * 0.5 }}
              />
            ))}

            {/* Rotating ring */}
            <motion.div
              className="absolute inset-[-20px] rounded-full border-2 border-dashed border-primary/20"
              animate={{ rotate: 360 }}
              transition={{ duration: 30, repeat: Infinity, ease: "linear" }}
            />

            {/* Shield icon */}
            <div className="w-full h-full rounded-full bg-gradient-to-br from-primary/10 to-accent/10 flex items-center justify-center backdrop-blur-sm border border-primary/20">
              <Shield size={80} className="text-primary" style={{ filter: "drop-shadow(0 0 20px hsla(217,91%,60%,0.4))" }} />
            </div>

            {/* Particle sparks */}
            {[
              { top: "25%", left: "35%" },
              { top: "65%", left: "15%" },
              { top: "45%", left: "75%" },
              { top: "75%", left: "55%" },
              { top: "30%", left: "65%" },
            ].map((pos, i) => (
              <motion.div key={i}
                className="absolute w-1.5 h-1.5 rounded-full bg-primary"
                style={pos}
                animate={{ opacity: [0, 1, 0], scale: [0, 1.5, 0] }}
                transition={{ duration: 2, repeat: Infinity, delay: i * 0.7 }}
              />
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
}
