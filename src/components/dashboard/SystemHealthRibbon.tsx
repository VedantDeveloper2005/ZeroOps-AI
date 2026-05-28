"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";

interface HealthItem {
  name: string;
  status: "healthy" | "warning" | "critical";
  detail: string;
}

export function SystemHealthRibbon() {
  const [items, setItems] = useState<HealthItem[]>([]);

  useEffect(() => {
    async function fetchHealth() {
      try {
        const data = await api.getHealth();
        // Build health items from backend health response
        const healthItems: HealthItem[] = [
          { name: "API Status", status: data.status === "ok" ? "healthy" : "warning", detail: data.status === "ok" ? "Operational" : "Degraded" },
          { name: "AI Engine", status: data.openAIConfigured ? "healthy" : "warning", detail: data.openAIConfigured ? "Online" : "Not configured" },
          { name: "Environment", status: "healthy", detail: data.environment || "production" },
        ];
        setItems(healthItems);
      } catch {
        setItems([
          { name: "API Status", status: "warning", detail: "Connecting..." },
        ]);
      }
    }
    fetchHealth();
  }, []);

  if (items.length === 0) return null;

  const statusColor = (s: string) =>
    s === "healthy" ? "bg-emerald-400" : s === "warning" ? "bg-amber-400" : "bg-red-400";

  return (
    <div className="flex items-center gap-4 px-4 py-1.5 border-b border-border bg-background-secondary text-xs overflow-x-auto no-scrollbar">
      {items.map((item) => (
        <div key={item.name} className="flex items-center gap-1.5 flex-shrink-0">
          <span className={`w-1.5 h-1.5 rounded-full ${statusColor(item.status)}`} />
          <span className="text-foreground-muted">{item.name}:</span>
          <span className="text-foreground font-medium">{item.detail}</span>
        </div>
      ))}
    </div>
  );
}
