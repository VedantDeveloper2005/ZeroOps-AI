"use client";

import { motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { Loader2, Search } from "lucide-react";
import { api, type Deployment, type DeploymentLog } from "@/lib/api";
import { useNotifications } from "@/lib/NotificationContext";

const levels = ["info", "warning", "error", "debug"] as const;
const levelColor: Record<string, string> = {
  info: "bg-primary/10 text-primary", warning: "bg-warning/10 text-warning", error: "bg-danger/10 text-danger", debug: "bg-foreground-muted/10 text-foreground-muted",
};

export default function LogsPage() {
  const { projects } = useNotifications();
  const [selectedProject, setSelectedProject] = useState("");
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [logs, setLogs] = useState<DeploymentLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [activeLevels, setActiveLevels] = useState<Set<string>>(new Set(levels));

  useEffect(() => { if (projects.length && !selectedProject) setSelectedProject(projects[0].id); }, [projects, selectedProject]);

  useEffect(() => {
    if (!selectedProject) return;
    setLoading(true);
    api.getDeployments(100)
      .then((items) => setDeployments(items.filter((item) => item.project_id === selectedProject)))
      .catch(() => setDeployments([]))
      .finally(() => setLoading(false));
  }, [selectedProject]);

  const latest = deployments[0];
  const latestDeploymentId = latest?.id;
  useEffect(() => {
    if (!latestDeploymentId) { setLogs([]); return; }
    setLoading(true);
    api.getDeployment(latestDeploymentId)
      .then((detail) => setLogs(detail.logs || []))
      .catch(() => setLogs([]))
      .finally(() => setLoading(false));
  }, [latestDeploymentId]);

  const filtered = useMemo(() => logs.filter((log) => {
    const level = log.level.toLowerCase();
    return activeLevels.has(level) && (!search || log.message.toLowerCase().includes(search.toLowerCase()));
  }), [logs, search, activeLevels]);

  const toggleLevel = (level: string) => setActiveLevels((current) => {
    const next = new Set(current);
    if (next.has(level)) next.delete(level);
    else next.add(level);
    return next;
  });

  return <div className="flex h-full flex-col space-y-4">
    <div className="flex flex-wrap items-center gap-3">
      <label className="flex max-w-md flex-1 items-center gap-2 rounded-xl border border-border bg-card px-4 py-2 shadow-sm"><Search size={16} className="text-foreground-muted" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search recorded logs" className="w-full border-none bg-transparent text-xs font-semibold text-foreground outline-none placeholder:text-foreground-muted" /></label>
      <select value={selectedProject} onChange={(event) => setSelectedProject(event.target.value)} className="cursor-pointer rounded-xl border border-border bg-card px-3 py-2 text-xs font-semibold text-foreground shadow-sm outline-none focus:ring-1 focus:ring-primary">{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select>
      <div className="flex gap-1.5 rounded-lg border border-border/50 bg-background-secondary p-0.5">{levels.map((level) => <button key={level} onClick={() => toggleLevel(level)} className={`cursor-pointer rounded-md px-3 py-1.5 text-[10px] font-bold uppercase transition ${activeLevels.has(level) ? `${levelColor[level]} border border-border/40 shadow-sm` : "text-foreground-muted hover:text-foreground"}`}>{level}</button>)}</div>
    </div>
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex-1 overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      <div className="border-b border-border bg-background-secondary px-4 py-3 text-[10px] font-bold uppercase tracking-wider text-foreground-muted">{latest ? `Latest deployment · ${filtered.length} recorded entries` : "No deployment selected"}</div>
      <div className="max-h-[calc(100vh-320px)] overflow-y-auto bg-background-secondary/40 p-4 font-mono text-[11px] leading-7">
        {loading ? <div className="flex items-center gap-2 text-foreground-muted"><Loader2 className="h-4 w-4 animate-spin text-primary" />Loading recorded logs…</div> : filtered.map((log) => { const level = log.level.toLowerCase(); return <div key={`${log.line_number}-${log.timestamp}`} className="flex gap-3 rounded px-2 py-0.5 hover:bg-card/40"><span className="w-24 shrink-0 font-bold text-foreground-muted">{log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : "—"}</span><span className={`w-16 shrink-0 rounded py-0.5 text-center text-[9px] font-bold ${levelColor[level] || levelColor.info}`}>{level}</span><span className={level === "error" ? "text-danger" : level === "warning" ? "text-warning" : "text-foreground"}>{log.message}</span></div>; })}
        {!loading && !filtered.length && <p className="text-foreground-muted">No recorded log entries match this view. Logs appear after a deployment starts.</p>}
      </div>
    </motion.div>
  </div>;
}
