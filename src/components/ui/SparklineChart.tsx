"use client";

import { useMemo, useId } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface SparklineChartProps {
  data: number[];
  color?: string;
  width?: number;
  height?: number;
  className?: string;
  showGradient?: boolean;
  strokeWidth?: number;
}

export default function SparklineChart({
  data,
  color = "hsl(217, 91%, 60%)",
  width = 120,
  height = 40,
  className,
  showGradient = true,
  strokeWidth = 2,
}: SparklineChartProps) {
  const id = useId();
  const gradientId = `sparkline-grad-${id}`;

  const { polylinePoints, areaPath } = useMemo(() => {
    if (data.length < 2) return { polylinePoints: "", areaPath: "" };

    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const padding = 2;
    const chartWidth = width - padding * 2;
    const chartHeight = height - padding * 2;

    const points = data.map((val, i) => {
      const x = padding + (i / (data.length - 1)) * chartWidth;
      const y = padding + chartHeight - ((val - min) / range) * chartHeight;
      return { x, y };
    });

    const polylinePoints = points.map((p) => `${p.x},${p.y}`).join(" ");

    // Create area path (line + close via bottom)
    const areaPath = [
      `M ${points[0].x},${points[0].y}`,
      ...points.slice(1).map((p) => `L ${p.x},${p.y}`),
      `L ${points[points.length - 1].x},${height}`,
      `L ${points[0].x},${height}`,
      "Z",
    ].join(" ");

    return { polylinePoints, areaPath };
  }, [data, width, height]);

  if (data.length < 2) return null;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={cn("overflow-visible", className)}
      fill="none"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.3} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>

      {/* Gradient fill area */}
      {showGradient && (
        <motion.path
          d={areaPath}
          fill={`url(#${gradientId})`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 1, delay: 0.5 }}
        />
      )}

      {/* Main line */}
      <motion.polyline
        points={polylinePoints}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: 1, opacity: 1 }}
        transition={{ duration: 1.2, ease: "easeInOut" }}
      />
    </svg>
  );
}
