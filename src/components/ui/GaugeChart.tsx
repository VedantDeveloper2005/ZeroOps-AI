"use client";

import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { cn } from "@/lib/utils";

interface GaugeChartProps {
  value: number;
  maxValue?: number;
  label?: string;
  color?: string;
  size?: number;
  className?: string;
}

export function GaugeChart({ value, maxValue = 100, label, color, size = 160, className }: GaugeChartProps) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });
  const percentage = Math.min(value / maxValue, 1);
  const radius = (size - 20) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference * (1 - percentage);

  const autoColor = !color
    ? percentage < 0.6 ? "hsl(142, 76%, 45%)" : percentage < 0.8 ? "hsl(38, 92%, 50%)" : "hsl(0, 84%, 60%)"
    : color;

  return (
    <div ref={ref} className={cn("relative flex flex-col items-center justify-center", className)}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="transform -rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="hsl(228, 15%, 12%)" strokeWidth="8" />
        <motion.circle
          cx={size / 2} cy={size / 2} r={radius} fill="none"
          stroke={autoColor} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={isInView ? { strokeDashoffset } : { strokeDashoffset: circumference }}
          transition={{ duration: 1.5, ease: "easeOut", delay: 0.2 }}
          style={{ filter: `drop-shadow(0 0 6px ${autoColor})` }}
        />
      </svg>
      <div className="absolute flex flex-col items-center justify-center" style={{ width: size, height: size }}>
        <span className="text-3xl font-bold text-foreground">{value}</span>
        {label && <span className="text-xs text-foreground-muted mt-1">{label}</span>}
      </div>
    </div>
  );
}
