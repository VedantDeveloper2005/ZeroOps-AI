"use client";

import { motion } from "framer-motion";
import { useState, useEffect } from "react";
import { Server, Box, Hexagon, Activity, Loader2, Database } from "lucide-react";
import { api, type Project } from "@/lib/api";
import { useNotifications } from "@/lib/NotificationContext";
import { LockedView } from "@/components/dashboard/LockedView";

interface InfraNode {
  id: string;
  name: string;
  type: "cluster" | "node" | "pod" | "service" | "deployment";
  status: "healthy" | "warning" | "critical";
  cpu: number;
  memory: number;
  connections: string[];
  x: number;
  y: number;
}

const statusColor = (status: string) => {
  switch (status) { 
    case "healthy": return { fill: "#22c55e", stroke: "#22c55e40", glow: "0 0 12px #22c55e40" }; 
    case "warning": return { fill: "#f59e0b", stroke: "#f59e0b40", glow: "0 0 12px #f59e0b40" }; 
    default: return { fill: "#ef4444", stroke: "#ef444440", glow: "0 0 12px #ef444440" }; 
  }
};

export default function InfrastructurePage() {
  const { hasDeployed } = useNotifications();

  if (!hasDeployed) {
    return (
      <div className="space-y-6">
        <LockedView featureName="Infrastructure Topology" />
      </div>
    );
  }

  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    async function loadProjects() {
      try {
        const projs = await api.getProjects();
        setProjects(projs);
        if (projs.length > 0) {
          setSelectedProjectId(projs[0].id);
        }
      } catch (err) {
        console.error("Failed to load projects", err);
      } finally {
        setLoading(false);
      }
    }
    loadProjects();
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <p className="text-foreground-muted text-sm font-medium">Loading infrastructure topology...</p>
      </div>
    );
  }

  const selectedProject = projects.find(p => p.id === selectedProjectId);
  
  const infraNodes: InfraNode[] = [];
  if (selectedProject) {
    const regionName = selectedProject.region || "eastus";
    const appName = selectedProject.name;
    const isFailed = selectedProject.status === "failed";
    const statusVal = isFailed ? "warning" as const : "healthy" as const;
    const podStatusVal = isFailed ? "critical" as const : "healthy" as const;
    
    // Cluster
    infraNodes.push({
      id: "cluster-1",
      name: `aks-prod-${regionName}`,
      type: "cluster",
      status: statusVal,
      cpu: isFailed ? 15 : 62,
      memory: isFailed ? 25 : 68,
      connections: ["node-1", "node-2"],
      x: 450,
      y: 80
    });
    
    // Nodes
    infraNodes.push(
      { id: "node-1", name: `aks-nodepool1-vm0`, type: "node", status: "healthy", cpu: 45, memory: 58, connections: ["pod-1", "pod-2"], x: 280, y: 220 },
      { id: "node-2", name: `aks-nodepool1-vm1`, type: "node", status: statusVal, cpu: isFailed ? 10 : 79, memory: isFailed ? 20 : 72, connections: ["pod-3", "pod-4"], x: 620, y: 220 }
    );
    
    // Pods
    infraNodes.push(
      { id: "pod-1", name: `${appName}-prod-a1b2c`, type: "pod", status: podStatusVal, cpu: isFailed ? 0 : 12, memory: isFailed ? 0 : 65, connections: ["svc-app"], x: 180, y: 380 },
      { id: "pod-2", name: `${appName}-prod-d3e4f`, type: "pod", status: podStatusVal, cpu: isFailed ? 0 : 18, memory: isFailed ? 0 : 68, connections: ["svc-app"], x: 320, y: 380 },
      { id: "pod-3", name: `${appName}-prod-g5h6i`, type: "pod", status: podStatusVal, cpu: isFailed ? 0 : 5, memory: isFailed ? 0 : 60, connections: ["svc-app"], x: 580, y: 380 },
      { id: "pod-4", name: `${appName}-prod-j7k8l`, type: "pod", status: podStatusVal, cpu: isFailed ? 0 : 14, memory: isFailed ? 0 : 64, connections: ["svc-app"], x: 720, y: 380 }
    );
    
    // Service
    infraNodes.push({
      id: "svc-app",
      name: `${appName}-svc`,
      type: "service",
      status: statusVal,
      cpu: 0,
      memory: 0,
      connections: [],
      x: 450,
      y: 500
    });
  }

  const hovered = infraNodes.find(n => n.id === hoveredId);
  const clusters = infraNodes.filter(n => n.type === "cluster");
  const nodes = infraNodes.filter(n => n.type === "node");
  const pods = infraNodes.filter(n => n.type === "pod");
  const services = infraNodes.filter(n => n.type === "service");

  return (
    <div className="space-y-6">
      {/* Header and project selector */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-card border border-border rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10 border border-primary/20 text-primary">
            <Database size={20} />
          </div>
          <div>
            <h2 className="text-sm font-bold text-foreground">Infrastructure Target</h2>
            <p className="text-[10px] text-foreground-muted">Select connected project to view active Kubernetes resources and topology nodes.</p>
          </div>
        </div>
        
        <div className="flex items-center gap-3 self-end sm:self-auto">
          <select
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="bg-background-secondary border border-border text-xs rounded-lg px-3 py-1.5 text-foreground focus:outline-none focus:ring-1 focus:ring-primary font-semibold max-w-[200px]"
          >
            {projects.map(p => (
              <option key={p.id} value={p.id}>{p.full_name}</option>
            ))}
          </select>

          <div className="flex gap-2">
            <button onClick={() => setZoom(z => Math.max(0.5, z - 0.1))} className="px-2.5 py-1 bg-background-secondary border border-border/80 rounded-md text-xs font-semibold hover:bg-background transition cursor-pointer select-none shadow-sm">−</button>
            <span className="text-xs text-foreground-muted w-10 text-center font-mono font-semibold leading-7">{Math.round(zoom * 100)}%</span>
            <button onClick={() => setZoom(z => Math.min(1.5, z + 0.1))} className="px-2.5 py-1 bg-background-secondary border border-border/80 rounded-md text-xs font-semibold hover:bg-background transition cursor-pointer select-none shadow-sm">+</button>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-4 gap-4">
        {/* Topology */}
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="lg:col-span-3 bg-card border border-border rounded-xl p-6 overflow-auto relative shadow-sm" style={{ minHeight: 560 }}>
          {selectedProject ? (
            <svg viewBox="0 0 900 560" className="w-full min-w-[800px]" style={{ transform: `scale(${zoom})`, transformOrigin: "top left" }}>
              {/* Connection lines */}
              {infraNodes.map(node => node.connections.map(targetId => {
                const target = infraNodes.find(n => n.id === targetId);
                if (!target) return null;
                return (
                  <g key={`${node.id}-${targetId}`}>
                    <line x1={node.x} y1={node.y} x2={target.x} y2={target.y} stroke="hsla(217, 91%, 60%, 0.15)" strokeWidth="1" />
                    {/* Animated flow dot */}
                    <motion.circle r="2" fill="#3b82f6" opacity={0.6}
                      animate={{ cx: [node.x, target.x], cy: [node.y, target.y] }}
                      transition={{ 
                        duration: 2 + ((node.x + target.y) % 3), 
                        repeat: Infinity, 
                        ease: "linear", 
                        delay: ((node.y + target.x) % 4) * 0.5 
                      }}
                    />
                  </g>
                );
              }))}

              {/* Cluster boundary */}
              {clusters.map(c => (
                <g key={c.id}>
                  <rect x={50} y={40} width={800} height={490} rx={16} fill="none" stroke="var(--border)" strokeWidth="1" strokeDasharray="8 4" />
                  <text x={60} y={30} fill="var(--primary)" fontSize="11" className="font-mono font-bold">{c.name}</text>
                </g>
              ))}

              {/* Nodes */}
              {nodes.map(n => {
                const colors = statusColor(n.status);
                return (
                  <g key={n.id} onMouseEnter={() => setHoveredId(n.id)} onMouseLeave={() => setHoveredId(null)} className="cursor-pointer">
                    <circle cx={n.x} cy={n.y} r={30} fill="var(--card)" stroke={colors.stroke} strokeWidth="1.5" style={{ filter: colors.glow }} />
                    <circle cx={n.x} cy={n.y} r={8} fill={colors.fill} opacity={0.6} />
                    <text x={n.x} y={n.y + 45} textAnchor="middle" fill="currentColor" className="text-foreground-muted font-bold font-mono text-[9px]">{n.name}</text>
                  </g>
                );
              })}

              {/* Pods */}
              {pods.map((p, i) => {
                const colors = statusColor(p.status);
                return (
                  <motion.g key={p.id} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: i * 0.03 }}
                    onMouseEnter={() => setHoveredId(p.id)} onMouseLeave={() => setHoveredId(null)} className="cursor-pointer">
                    <circle cx={p.x} cy={p.y} r={14} fill="var(--card)" stroke={colors.stroke} strokeWidth="1" />
                    <circle cx={p.x} cy={p.y} r={5} fill={colors.fill}>
                      {p.status !== "healthy" && <animate attributeName="opacity" values="1;0.4;1" dur="1.5s" repeatCount="indefinite" />}
                    </circle>
                  </motion.g>
                );
              })}

              {/* Services */}
              {services.map(s => {
                const colors = statusColor(s.status);
                return (
                  <g key={s.id} onMouseEnter={() => setHoveredId(s.id)} onMouseLeave={() => setHoveredId(null)} className="cursor-pointer">
                    <polygon points={`${s.x},${s.y - 16} ${s.x + 16},${s.y} ${s.x},${s.y + 16} ${s.x - 16},${s.y}`} fill="var(--card)" stroke={colors.stroke} strokeWidth="1" />
                    <circle cx={s.x} cy={s.y} r={4} fill={colors.fill} />
                    <text x={s.x} y={s.y + 28} textAnchor="middle" fill="currentColor" className="text-foreground-muted font-bold font-mono text-[8px]">{s.name}</text>
                  </g>
                );
              })}
            </svg>
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-xs text-foreground-muted">No projects active</div>
          )}

          {/* Hover tooltip */}
          {hovered && (
            <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
              className="absolute bg-card border border-border rounded-xl p-4 z-20 w-52 pointer-events-none shadow-lg" style={{ left: Math.min(hovered.x + 20, 700), top: Math.min(hovered.y + 20, 480) }}>
              <p className="text-xs font-bold text-foreground mb-1">{hovered.name}</p>
              <p className="text-[10px] text-foreground-muted uppercase font-bold tracking-wider mb-2">{hovered.type}</p>
              <div className="flex items-center gap-2 mb-2"><span className={`w-2.5 h-2.5 rounded-full ${hovered.status === "healthy" ? "bg-success" : hovered.status === "warning" ? "bg-warning" : "bg-danger"}`} /><span className="text-xs font-bold capitalize">{hovered.status}</span></div>
              {hovered.cpu > 0 && <div className="text-[10px] text-foreground-muted font-mono font-semibold">CPU: {hovered.cpu}% • Memory: {hovered.memory}%</div>}
            </motion.div>
          )}
        </motion.div>

        {/* Stats sidebar */}
        <div className="space-y-4">
          {[{ label: "Nodes", value: nodes.length, icon: Server, color: "text-primary" }, { label: "Pods", value: pods.length, icon: Box, color: "text-success" }, { label: "Services", value: services.length, icon: Hexagon, color: "text-accent" }, { label: "Healthy Assets", value: infraNodes.filter(n => n.status === "healthy").length, icon: Activity, color: "text-success" }].map((s, i) => (
            <motion.div key={s.label} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.1 }} className="bg-card border border-border rounded-xl p-4 flex items-center gap-3 shadow-sm">
              <s.icon size={20} className={s.color} />
              <div><p className="text-2xl font-bold text-foreground">{s.value}</p><p className="text-xs text-foreground-muted">{s.label}</p></div>
            </motion.div>
          ))}

          {/* Legend */}
          <div className="bg-card border border-border rounded-xl p-4 shadow-sm">
            <h4 className="text-[10px] font-bold text-foreground-muted mb-3 uppercase tracking-wider">LEGEND</h4>
            {[{ shape: "●", label: "Node", size: "30px" }, { shape: "●", label: "Pod", size: "14px" }, { shape: "◆", label: "Service", size: "20px" }].map(l => (
              <div key={l.label} className="flex items-center gap-2 text-xs font-semibold text-foreground-muted mb-1.5"><span className="text-primary">{l.shape}</span>{l.label}</div>
            ))}
            <hr className="border-border my-2.5" />
            {[{ color: "bg-success", label: "Healthy" }, { color: "bg-warning", label: "Warning" }, { color: "bg-danger", label: "Critical" }].map(s => (
              <div key={s.label} className="flex items-center gap-2 text-xs font-semibold text-foreground-muted mb-1.5"><div className={`w-2.5 h-2.5 rounded-full ${s.color}`} />{s.label}</div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
