"use client";

import { useEffect, useRef } from "react";
import {
  useMotionValue,
  useSpring,
  useInView,
  useTransform,
  motion,
} from "framer-motion";
import { cn } from "@/lib/utils";

export interface AnimatedCounterProps {
  value: number;
  suffix?: string;
  prefix?: string;
  duration?: number;
  decimals?: number;
  className?: string;
}

export default function AnimatedCounter({
  value,
  suffix = "",
  prefix = "",
  duration = 2,
  decimals = 0,
  className,
}: AnimatedCounterProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const motionValue = useMotionValue(0);
  const springValue = useSpring(motionValue, {
    damping: 40,
    stiffness: 100,
    duration: duration * 1000,
  });
  const isInView = useInView(ref, { once: true, margin: "-50px" });

  const display = useTransform(springValue, (latest) => {
    const formatted =
      decimals > 0
        ? latest.toFixed(decimals)
        : Math.round(latest).toLocaleString();
    return `${prefix}${formatted}${suffix}`;
  });

  useEffect(() => {
    if (isInView) {
      motionValue.set(value);
    }
  }, [isInView, value, motionValue]);

  return (
    <motion.span
      ref={ref}
      className={cn(
        "tabular-nums tracking-tight font-bold text-foreground",
        className
      )}
    >
      {display}
    </motion.span>
  );
}
