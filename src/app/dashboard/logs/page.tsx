"use client";

import { motion } from "framer-motion";
import { useState, useEffect } from "react";
import { Search } from "lucide-react";
import { logEntries } from "@/lib/mock-data";

const levels = ["INFO", "WARN", "ERROR", "DEBUG"] as const;
const levelColor: Record<string, string> = { 
  INFO: "bg-primary/10 text-primary", 
  WARN: "bg-warning/10 text-warning", 
  ERROR: "bg-danger/10 text-danger", 
  DEBUG: "bg-foreground-muted/10 text-foreground-muted" 
};

// Parse incoming log lines from WebSocket stream
const parseLogLine = (line: string, fallbackPod: string) => {
  try {
    const trimmed = line.trim();
    if (!trimmed) return null;

    // Matches: 19:59:19.456 [INFO] api-gateway-a1b2 - GET /api/v1/deployments 200 23ms
    const match = trimmed.match(/^([\d:.]+)\s+\[(INFO|WARN|ERROR|DEBUG)\]\s+([^\s]+)\s+-\s+(.*)$/);
    if (match) {
      return {
        id: `log-stream-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
        timestamp: match[1],
        level: match[2] as "INFO" | "WARN" | "ERROR" | "DEBUG",
        pod: match[3],
        message: match[4],
      };
    }

    // Fallback
    return {
      id: `log-stream-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
      timestamp: new Date().toLocaleTimeString(),
      level: "INFO" as const,
      pod: fallbackPod === "all" ? "cluster" : fallbackPod,
      message: trimmed,
    };
  } catch (e) {
    console.error("Error parsing log line:", e);
    return null;
  }
};

export default function LogsPage() {
  const [search, setSearch] = useState("");
  const [activeLevels, setActiveLevels] = useState<Set<string>>(new Set(levels));
  const [selectedPod, setSelectedPod] = useState("all");
  const [logs, setLogs] = useState<typeof logEntries>(logEntries);

  const toggleLevel = (level: string) => {
    const next = new Set(activeLevels);
    if (next.has(level)) {
      next.delete(level);
    } else {
      next.add(level);
    }
    setActiveLevels(next);
  };

  // Connect to backend WebSocket log stream
  useEffect(() => {
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsHost = window.location.hostname === "localhost" ? "localhost:8000" : window.location.host;
    
    // Connect to specific pod or 'all-pods' fallback
    const podParam = selectedPod === "all" ? "all-pods" : selectedPod;
    const socket = new WebSocket(`${wsProtocol}//${wsHost}/ws/logs/${podParam}`);

    socket.onopen = () => {
      console.log(`Logs WebSocket connected for pod: ${podParam}`);
    };

    socket.onmessage = (event) => {
      const parsed = parseLogLine(event.data, podParam);
      if (parsed) {
        setLogs((prev) => {
          const next = [...prev, parsed];
          // Keep a buffer of 300 logs
          if (next.length > 300) {
            return next.slice(next.length - 300);
          }
          return next;
        });
      }
    };

    socket.onerror = (err) => {
      console.error("Logs WebSocket error:", err);
    };

    return () => {
      socket.close();
    };
  }, [selectedPod]);

  // Derive unique list of pods from historical plus newly seen logs
  const uniquePods = Array.from(new Set([...logEntries.map((l) => l.pod), ...logs.map((l) => l.pod)]));

  const filtered = logs.filter(
    (l) =>
      activeLevels.has(l.level) &&
      (selectedPod === "all" || l.pod === selectedPod) &&
      (search === "" || l.message.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="space-y-4 h-full flex flex-col">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Logs</h1>
          <p className="text-foreground-muted text-sm mt-1">Real-time log stream from all pods</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="glass-subtle rounded-xl px-4 py-2 flex items-center gap-2 flex-1 max-w-md">
          <Search size={16} className="text-foreground-muted" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter logs..."
            className="bg-transparent border-none outline-none text-sm text-foreground placeholder:text-foreground-muted w-full"
          />
        </div>
        <select
          value={selectedPod}
          onChange={(e) => setSelectedPod(e.target.value)}
          className="glass-subtle rounded-xl px-3 py-2 text-sm text-foreground bg-background border border-border"
        >
          <option value="all" className="bg-background text-foreground">
            All Pods
          </option>
          {uniquePods.map((p) => (
            <option key={p} value={p} className="bg-background text-foreground">
              {p}
            </option>
          ))}
        </select>
        <div className="flex gap-1">
          {levels.map((l) => (
            <button
              key={l}
              onClick={() => toggleLevel(l)}
              className={`px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                activeLevels.has(l) ? levelColor[l] : "text-foreground-muted/30 bg-card/30"
              }`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      {/* Log viewer */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="glass rounded-xl overflow-hidden flex-1">
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border">
          <div className="w-2 h-2 rounded-full bg-success animate-pulse" />
          <span className="text-xs font-mono text-foreground-muted">Live stream — {filtered.length} entries</span>
        </div>
        <div
          className="p-4 font-mono text-xs leading-7 overflow-y-auto no-scrollbar bg-black/20"
          style={{ maxHeight: "calc(100vh - 320px)" }}
        >
          {filtered.map((log) => (
            <div key={log.id} className="flex gap-3 hover:bg-card/30 px-2 py-0.5 rounded">
              <span className="text-foreground-muted w-28 flex-shrink-0">{log.timestamp}</span>
              <span
                className={`w-14 text-center rounded text-[10px] font-semibold py-0.5 ${levelColor[log.level]}`}
              >
                {log.level}
              </span>
              <span className="text-foreground-muted w-40 truncate flex-shrink-0">{log.pod}</span>
              <span
                className={
                  log.level === "ERROR"
                    ? "text-danger"
                    : log.level === "WARN"
                    ? "text-warning"
                    : "text-foreground"
                }
              >
                {log.message}
              </span>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}

