"use client";

import { systemHealth } from "@/lib/mock-data";
import { motion } from "framer-motion";

export function SystemHealthRibbon() {
  return (
    <div className="h-11 bg-background-secondary border-b border-border flex items-center justify-center px-4 relative overflow-hidden">
      {/* Shimmer border effect */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-primary/20 to-transparent" />

      <div className="flex items-center gap-6 text-xs">
        {systemHealth.map((item, i) => (
          <motion.button
            key={item.name}
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05, duration: 0.3 }}
            className="flex items-center gap-2 hover:bg-card/50 px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
          >
            <span
              className={`status-dot ${
                item.status === "healthy"
                  ? "status-dot-green"
                  : item.status === "warning"
                  ? "status-dot-yellow"
                  : "status-dot-red"
              }`}
            />
            <span className="text-foreground font-medium whitespace-nowrap">{item.name}</span>
            <span className="text-foreground-muted hidden lg:inline whitespace-nowrap">{item.detail}</span>
          </motion.button>
        ))}
      </div>
    </div>
  );
}
