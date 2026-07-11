"use client";

import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { createReconnectingWebSocket } from "@/lib/runtime-config";
import { useNotifications } from "@/lib/NotificationContext";
import { api } from "@/lib/api";

const levels = ["INFO", "WARN", "ERROR", "DEBUG"] as const;
const levelColor: Record<string, string> = {
  INFO: "bg-primary/10 text-primary",
  WARN: "bg-warning/10 text-warning",
  ERROR: "bg-danger/10 text-danger",
  DEBUG: "bg-foreground-muted/10 text-foreground-muted",
};

interface LogEntry {
  id: string;
  timestamp: string;
  level: "INFO" | "WARN" | "ERROR" | "DEBUG";
  pod: string;
  message: string;
}

function createLogId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `log-stream-${Date.now()}`;
}

function parseLogLine(line: string, fallbackPod: string): LogEntry | null {
  try {
    const trimmed = line.trim();
    if (!trimmed) return null;

    const match = trimmed.match(/^([\d:.]+)\s+\[(INFO|WARN|ERROR|DEBUG)\]\s+([^\s]+)\s+-\s+(.*)$/);
    if (match) {
      return {
        id: createLogId(),
        timestamp: match[1],
        level: match[2] as LogEntry["level"],
        pod: match[3],
        message: match[4],
      };
    }

    return {
      id: createLogId(),
      timestamp: new Date().toLocaleTimeString(),
      level: "INFO",
      pod: fallbackPod === "all" ? "cluster" : fallbackPod,
      message: trimmed,
    };
  } catch (err) {
    console.error("Error parsing log line:", err);
    return null;
  }
}

export default function LogsPage() {
  const { projects } = useNotifications();
  const [selectedProject, setSelectedProject] = useState("");
  const [selectedPod, setSelectedPod] = useState("all");
  const [streamStatus, setStreamStatus] = useState<"connecting" | "live" | "unavailable">("connecting");
  const [search, setSearch] = useState("");
  const [activeLevels, setActiveLevels] = useState<Set<string>>(new Set(levels));
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (projects.length > 0 && !selectedProject) {
      setSelectedProject(projects[0].id);
    }
  }, [projects, selectedProject]);

  const toggleLevel = (level: string) => {
    const next = new Set(activeLevels);
    if (next.has(level)) {
      next.delete(level);
    } else {
      next.add(level);
    }
    setActiveLevels(next);
  };

  useEffect(() => {
    setStreamStatus("connecting");

    const podParam = selectedPod === "all" ? (selectedProject || "all-pods") : selectedPod;

    const cleanup = createReconnectingWebSocket(`/ws/logs/${podParam}`, {
      onOpen: () => {
        setStreamStatus("live");
      },
      onMessage: (event) => {
        const parsed = parseLogLine(event.data, podParam);
        if (parsed) {
          setLogs((prev) => {
            const next = [...prev, parsed];
            return next.length > 300 ? next.slice(next.length - 300) : next;
          });
        }
      },
      onError: () => {
        setStreamStatus("unavailable");
      },
      onClose: () => {
        setStreamStatus("unavailable");
      },
      maxRetries: 5,
    });

    return cleanup;
  }, [selectedPod, selectedProject]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs.length]);

  const uniquePods = Array.from(new Set(logs.map((log) => log.pod)));
  const filtered = logs.filter(
    (log) =>
      activeLevels.has(log.level) &&
      (selectedPod === "all" || log.pod === selectedPod) &&
      (search === "" || log.message.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="space-y-4 h-full flex flex-col">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="bg-card border border-border/80 rounded-xl px-4 py-2 flex items-center gap-2 flex-1 max-w-md shadow-sm">
          <Search size={16} className="text-foreground-muted" />
          <input
            type="text"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search stream / filter logs..."
            className="bg-transparent border-none outline-none text-xs text-foreground placeholder:text-foreground-muted w-full font-semibold"
          />
        </div>

        <select
          value={selectedProject}
          onChange={(event) => setSelectedProject(event.target.value)}
          className="rounded-xl px-3 py-2 text-xs font-semibold text-foreground bg-card border border-border/80 shadow-sm cursor-pointer outline-none focus:ring-1 focus:ring-primary"
        >
          <option value="">All Projects</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>{project.name}</option>
          ))}
        </select>

        <select
          value={selectedPod}
          onChange={(event) => setSelectedPod(event.target.value)}
          className="rounded-xl px-3 py-2 text-xs font-semibold text-foreground bg-card border border-border/80 shadow-sm cursor-pointer outline-none focus:ring-1 focus:ring-primary"
        >
          <option value="all">All Pods</option>
          {uniquePods.map((pod) => (
            <option key={pod} value={pod}>{pod}</option>
          ))}
        </select>

        <div className="flex gap-1.5 bg-background-secondary p-0.5 rounded-lg border border-border/50">
          {levels.map((level) => {
            const isActive = activeLevels.has(level);
            return (
              <button
                key={level}
                onClick={() => toggleLevel(level)}
                className={`px-3 py-1.5 rounded-md text-[10px] font-bold transition select-none cursor-pointer ${
                  isActive ? `${levelColor[level]} shadow-sm border border-border/40` : "text-foreground-muted hover:text-foreground"
                }`}
              >
                {level}
              </button>
            );
          })}
        </div>
      </div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="bg-card border border-border rounded-xl overflow-hidden flex-1 shadow-sm"
      >
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-background-secondary">
          <div className={`w-2 h-2 rounded-full ${streamStatus === "live" ? "bg-success animate-pulse" : "bg-foreground-muted"}`} />
          <span className="text-[10px] uppercase font-bold text-foreground-muted font-mono tracking-wider">
            {streamStatus === "live" ? "Live stream" : streamStatus === "connecting" ? "Connecting" : "Stream unavailable"} - {filtered.length} entries
          </span>
        </div>
        <div
          ref={scrollRef}
          className="p-4 font-mono text-[11px] leading-7 overflow-y-auto no-scrollbar bg-background-secondary/40"
          style={{ maxHeight: "calc(100vh - 320px)" }}
        >
          {filtered.map((log) => (
            <div key={log.id} className="flex gap-3 hover:bg-card/40 px-2 py-0.5 rounded border border-transparent hover:border-border/20 transition-colors">
              <span className="text-foreground-muted w-24 flex-shrink-0 font-bold">{log.timestamp}</span>
              <span className={`w-14 text-center rounded text-[9px] font-bold py-0.5 shrink-0 ${levelColor[log.level]}`}>
                {log.level}
              </span>
              <span className="text-foreground-muted w-36 truncate flex-shrink-0 font-bold">{log.pod}</span>
              <span className={`truncate ${log.level === "ERROR" ? "text-danger" : log.level === "WARN" ? "text-warning" : "text-foreground"}`}>
                {log.message}
              </span>
            </div>
          ))}
          {filtered.length === 0 && (
            <p className="text-foreground-muted">
              {streamStatus === "unavailable"
                ? "Live log stream is unavailable. Start the backend WebSocket service or open a recorded deployment log."
                : "No log lines received yet."}
            </p>
          )}
        </div>
      </motion.div>
    </div>
  );
}
