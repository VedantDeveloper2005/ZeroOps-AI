"use client";

import { motion, useInView } from "framer-motion";
import { useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface DataPoint { time: string; value: number; }

interface AreaChartProps {
  data: DataPoint[];
  color?: string;
  height?: number;
  className?: string;
  showGrid?: boolean;
  showLabels?: boolean;
}

export function AreaChart({ data, color = "#3b82f6", height = 200, className, showGrid = true, showLabels = true }: AreaChartProps) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  if (!data.length) return null;

  const padding = { top: 10, right: 10, bottom: showLabels ? 30 : 10, left: showLabels ? 40 : 10 };
  const w = 600;
  const h = height;
  const chartW = w - padding.left - padding.right;
  const chartH = h - padding.top - padding.bottom;

  const minVal = Math.min(...data.map(d => d.value)) * 0.9;
  const maxVal = Math.max(...data.map(d => d.value)) * 1.1;

  const points = data.map((d, i) => ({
    x: padding.left + (i / (data.length - 1)) * chartW,
    y: padding.top + chartH - ((d.value - minVal) / (maxVal - minVal)) * chartH,
  }));

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${padding.top + chartH} L ${points[0].x} ${padding.top + chartH} Z`;
  const gradientId = `gradient-${color.replace("#", "")}`;

  return (
    <div ref={ref} className={cn("w-full relative", className)}>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height }}>
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.3" />
            <stop offset="100%" stopColor={color} stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {showGrid && Array.from({ length: 5 }).map((_, i) => {
          const y = padding.top + (i / 4) * chartH;
          return <line key={i} x1={padding.left} y1={y} x2={w - padding.right} y2={y} stroke="hsl(228, 15%, 12%)" strokeWidth="1" />;
        })}

        <motion.path
          d={areaPath} fill={`url(#${gradientId})`}
          initial={{ opacity: 0 }} animate={isInView ? { opacity: 1 } : {}}
          transition={{ duration: 1, delay: 0.3 }}
        />
        <motion.path
          d={linePath} fill="none" stroke={color} strokeWidth="2"
          initial={{ pathLength: 0 }} animate={isInView ? { pathLength: 1 } : {}}
          transition={{ duration: 1.5, ease: "easeOut" }}
        />

        {showLabels && data.filter((_, i) => i % Math.ceil(data.length / 6) === 0).map((d, i) => {
          const idx = i * Math.ceil(data.length / 6);
          return (
            <text key={i} x={points[idx]?.x || 0} y={h - 5} textAnchor="middle" fill="hsl(228, 10%, 40%)" fontSize="10">
              {d.time}
            </text>
          );
        })}

        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={hoveredIndex === i ? 5 : 0} fill={color}
            onMouseEnter={() => setHoveredIndex(i)} onMouseLeave={() => setHoveredIndex(null)}
            className="cursor-pointer transition-all" style={{ filter: `drop-shadow(0 0 4px ${color})` }}
          />
        ))}

        {/* Invisible hover targets */}
        {points.map((p, i) => (
          <rect key={`hover-${i}`} x={p.x - chartW / data.length / 2} y={padding.top} width={chartW / data.length} height={chartH}
            fill="transparent" onMouseEnter={() => setHoveredIndex(i)} onMouseLeave={() => setHoveredIndex(null)} className="cursor-pointer" />
        ))}
      </svg>

      {hoveredIndex !== null && (
        <div className="absolute glass rounded-lg px-3 py-1.5 text-xs pointer-events-none z-10"
          style={{ left: `${(points[hoveredIndex].x / w) * 100}%`, top: `${(points[hoveredIndex].y / h) * 100 - 15}%`, transform: "translateX(-50%)" }}>
          <span className="text-foreground font-medium">{data[hoveredIndex].value.toFixed(1)}</span>
          <span className="text-foreground-muted ml-1">{data[hoveredIndex].time}</span>
        </div>
      )}
    </div>
  );
}
