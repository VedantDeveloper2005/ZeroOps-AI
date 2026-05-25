"use client";

import { type ReactNode, useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

const glowColorMap = {
  blue: {
    border: "from-blue-500 via-blue-400 to-cyan-400",
    shadow: "0 0 30px hsla(217, 91%, 60%, 0.25), 0 0 60px hsla(217, 91%, 60%, 0.1), inset 0 0 30px hsla(217, 91%, 60%, 0.06)",
    gradient: "conic-gradient(from var(--border-angle, 0deg), transparent 40%, hsl(217, 91%, 60%) 70%, hsl(199, 89%, 48%) 85%, transparent 100%)",
  },
  purple: {
    border: "from-purple-500 via-violet-400 to-fuchsia-400",
    shadow: "0 0 30px hsla(265, 83%, 58%, 0.25), 0 0 60px hsla(265, 83%, 58%, 0.1), inset 0 0 30px hsla(265, 83%, 58%, 0.06)",
    gradient: "conic-gradient(from var(--border-angle, 0deg), transparent 40%, hsl(265, 83%, 58%) 70%, hsl(290, 80%, 55%) 85%, transparent 100%)",
  },
  green: {
    border: "from-green-500 via-emerald-400 to-teal-400",
    shadow: "0 0 30px hsla(142, 76%, 45%, 0.25), 0 0 60px hsla(142, 76%, 45%, 0.1), inset 0 0 30px hsla(142, 76%, 45%, 0.06)",
    gradient: "conic-gradient(from var(--border-angle, 0deg), transparent 40%, hsl(142, 76%, 45%) 70%, hsl(162, 72%, 45%) 85%, transparent 100%)",
  },
  cyan: {
    border: "from-cyan-500 via-sky-400 to-blue-400",
    shadow: "0 0 30px hsla(199, 89%, 48%, 0.25), 0 0 60px hsla(199, 89%, 48%, 0.1), inset 0 0 30px hsla(199, 89%, 48%, 0.06)",
    gradient: "conic-gradient(from var(--border-angle, 0deg), transparent 40%, hsl(199, 89%, 48%) 70%, hsl(217, 91%, 60%) 85%, transparent 100%)",
  },
} as const;

export interface GlowCardProps {
  children: ReactNode;
  className?: string;
  glowColor?: keyof typeof glowColorMap;
  hoverScale?: number;
}

export default function GlowCard({
  children,
  className,
  glowColor = "blue",
  hoverScale = 1.02,
}: GlowCardProps) {
  const colors = glowColorMap[glowColor];
  const [isHovered, setIsHovered] = useState(false);

  return (
    <motion.div
      className={cn(
        "glass relative rounded-xl p-[1px] transition-all duration-500",
        className
      )}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      whileHover={{
        scale: hoverScale,
        boxShadow: colors.shadow,
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{ willChange: "transform, box-shadow" }}
    >
      {/* Animated conic-gradient border */}
      <motion.div
        className="pointer-events-none absolute inset-[-1px] rounded-xl"
        style={{
          background: colors.gradient,
          animation: "border-rotate 4s linear infinite",
        }}
        initial={{ opacity: 0 }}
        animate={{ opacity: isHovered ? 1 : 0 }}
        transition={{ duration: 0.4 }}
      />

      {/* Inner card surface */}
      <div className="relative z-10 rounded-xl bg-card p-6">{children}</div>
    </motion.div>
  );
}
