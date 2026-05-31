"use client";

import React from "react";
import { motion } from "framer-motion";
import { Lock, Rocket, ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";

interface LockedViewProps {
  featureName: string;
  description?: string;
}

export function LockedView({
  featureName,
  description = "This operations panel is locked until you deploy your first application. ZeroOps AI requires an active production deployment to stream logs, audit security compliance, trace bottlenecks, and configure autoscaling."
}: LockedViewProps) {
  const router = useRouter();

  return (
    <div className="relative w-full min-h-[450px] rounded-2xl overflow-hidden glass p-8 flex flex-col items-center justify-center text-center space-y-6 border border-border/40 shadow-2xl">
      {/* Blurred background preview elements */}
      <div className="absolute inset-0 bg-background/40 backdrop-blur-md z-10" />
      <div className="absolute -top-10 -left-10 w-48 h-48 bg-primary/20 rounded-full blur-3xl opacity-50" />
      <div className="absolute -bottom-10 -right-10 w-48 h-48 bg-accent/20 rounded-full blur-3xl opacity-50" />
      
      {/* Background decoration representing locked logs/charts */}
      <div className="absolute inset-0 flex flex-col justify-around p-8 opacity-10 pointer-events-none select-none font-mono text-left text-[10px]">
        <div>[09:04:12] INFO auth-service - JWT token validated for user_id=usr_2847</div>
        <div>[09:04:15] WARN payments-service - DB connection pool at 82% capacity</div>
        <div className="flex gap-2 items-end h-8">
          <div className="bg-primary w-2 h-4" />
          <div className="bg-primary w-2 h-6" />
          <div className="bg-primary w-2 h-5" />
          <div className="bg-primary w-2 h-8" />
        </div>
        <div>[09:04:20] INFO api-gateway - GET /api/deployments 200 12ms</div>
      </div>

      {/* Lock Card Content */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4 }}
        className="relative z-20 max-w-md flex flex-col items-center space-y-6"
      >
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-lg glow-blue relative">
          <Lock size={28} className="text-white" />
          <span className="absolute -top-1 -right-1 flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-accent"></span>
          </span>
        </div>

        <div className="space-y-2">
          <h2 className="text-2xl font-bold tracking-tight text-foreground">{featureName}</h2>
          <p className="text-sm text-foreground-muted leading-relaxed">
            {description}
          </p>
        </div>

        <button
          onClick={() => router.push("/dashboard/repositories")}
          className="flex items-center gap-2 px-6 py-3 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary-hover transition-all glow-blue cursor-pointer group"
        >
          <Rocket size={16} />
          Deploy Your First Application
          <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform" />
        </button>
      </motion.div>
    </div>
  );
}
