"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { Check } from "lucide-react";
import { ReactNode } from "react";

interface TimelineEntryProps {
  icon: ReactNode;
  title: string;
  description?: string;
  timestamp: string;
  status: "completed" | "active" | "pending";
  color?: string;
  isLast?: boolean;
  index?: number;
}

export function TimelineEntry({ icon, title, description, timestamp, status, isLast = false, index = 0 }: TimelineEntryProps) {
<<<<<<< HEAD
=======
  const dotColors = {
    completed: "bg-success",
    active: "bg-primary status-dot-blue",
    pending: "bg-foreground-muted/30",
  };

>>>>>>> 7a8a49ab91a776be547d07446a274f5d8f0822b2
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: true }}
      transition={{ delay: index * 0.1, duration: 0.4 }}
      className="flex gap-4 relative"
    >
      {/* Timeline line */}
      {!isLast && (
        <div className="absolute left-[15px] top-[36px] bottom-0 w-px bg-border" />
      )}

      {/* Dot */}
      <div className={cn("w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 mt-1 relative z-10 border-2 border-background",
        status === "completed" ? "bg-success/20" : status === "active" ? "bg-primary/20" : "bg-card"
      )}>
        {status === "completed" ? (
          <Check size={14} className="text-success" />
        ) : status === "active" ? (
          <div className="w-3 h-3 rounded-full bg-primary animate-pulse" />
        ) : (
          <div className="w-2 h-2 rounded-full bg-foreground-muted/40" />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 pb-6">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-foreground-muted">{icon}</span>
            <h4 className={cn("text-sm font-medium", status === "pending" ? "text-foreground-muted" : "text-foreground")}>{title}</h4>
          </div>
          <span className="text-xs text-foreground-muted whitespace-nowrap">{timestamp}</span>
        </div>
        {description && <p className="text-xs text-foreground-muted mt-1">{description}</p>}
      </div>
    </motion.div>
  );
}
