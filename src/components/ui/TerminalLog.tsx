"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";

export interface TerminalLine {
  text: string;
  type: "command" | "info" | "success" | "warning" | "error" | "blank";
}

export interface TerminalLogProps {
  lines: TerminalLine[];
  speed?: number;
  autoScroll?: boolean;
  className?: string;
  title?: string;
}

const lineTypeStyles: Record<TerminalLine["type"], string> = {
  command: "text-white font-bold",
  info: "text-foreground-muted",
  success: "text-success",
  warning: "text-warning",
  error: "text-danger",
  blank: "",
};

export default function TerminalLog({
  lines,
  speed = 80,
  autoScroll = true,
  className,
  title = "zeroops-terminal",
}: TerminalLogProps) {
  const [visibleCount, setVisibleCount] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (visibleCount >= lines.length) return;

    const timer = setTimeout(() => {
      setVisibleCount((prev) => prev + 1);
    }, speed);

    return () => clearTimeout(timer);
  }, [visibleCount, lines.length, speed]);

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [visibleCount, autoScroll]);

  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border border-border bg-[hsl(228,15%,3%)]",
        className
      )}
    >
      {/* Window chrome header */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <div className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-full bg-[#ff5f57]" />
          <span className="h-3 w-3 rounded-full bg-[#febc2e]" />
          <span className="h-3 w-3 rounded-full bg-[#28c840]" />
        </div>
        <span className="ml-3 text-xs font-medium text-foreground-muted">
          {title}
        </span>
      </div>

      {/* Terminal body */}
      <div
        ref={scrollRef}
        className="h-64 overflow-y-auto p-4 font-mono text-sm leading-relaxed no-scrollbar"
      >
        <AnimatePresence>
          {lines.slice(0, visibleCount).map((line, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.15 }}
              className={cn(
                "min-h-[1.5em]",
                lineTypeStyles[line.type]
              )}
            >
              {line.type === "command" && (
                <span className="mr-2 text-success">❯</span>
              )}
              {line.text}
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Blinking cursor */}
        <motion.span
          className="inline-block h-4 w-[2px] translate-y-[2px] bg-success"
          animate={{ opacity: [1, 0] }}
          transition={{ duration: 0.8, repeat: Infinity, repeatType: "reverse" }}
        />
      </div>
    </div>
  );
}
