"use client";

import { motion } from "framer-motion";
import { Brain } from "lucide-react";
import { cn } from "@/lib/utils";

interface AIThinkingIndicatorProps {
  label?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function AIThinkingIndicator({ label = "AI Processing", size = "md", className }: AIThinkingIndicatorProps) {
  const sizes = { sm: { icon: 16, dot: 4, gap: 1 }, md: { icon: 20, dot: 6, gap: 1.5 }, lg: { icon: 28, dot: 8, gap: 2 } };
  const s = sizes[size];

  return (
    <div className={cn("flex items-center gap-3", className)}>
      <Brain size={s.icon} className="text-primary" style={{ filter: "drop-shadow(0 0 8px hsla(217,91%,60%,0.4))" }} />
      <div className="flex items-center" style={{ gap: `${s.gap * 4}px` }}>
        {[0, 1, 2].map((i) => (
          <motion.div
            key={i}
            className="rounded-full bg-primary"
            style={{ width: s.dot, height: s.dot }}
            animate={{ y: [0, -s.dot * 1.5, 0], opacity: [0.4, 1, 0.4] }}
            transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.15, ease: "easeInOut" }}
          />
        ))}
      </div>
      {label && <span className="text-xs text-foreground-muted">{label}</span>}
    </div>
  );
}
