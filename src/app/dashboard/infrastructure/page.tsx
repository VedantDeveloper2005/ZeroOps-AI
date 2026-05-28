"use client";

import { motion } from "framer-motion";
import { useState } from "react";
import { Server, Box, Hexagon, Activity } from "lucide-react";
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

const infraNodes: InfraNode[] = [
  { id: "cluster-1", name: "aks-prod-eastus", type: "cluster", status: "healthy", cpu: 67, memory: 72, connections: ["node-1", "node-2", "node-3"], x: 400, y: 80 },
  { id: "node-1", name: "aks-nodepool1-vm0", type: "node", status: "healthy", cpu: 78, memory: 65, connections: ["pod-1", "pod-2", "pod-3", "pod-4"], x: 200, y: 220 },
  { id: "node-2", name: "aks-nodepool1-vm1", type: "node", status: "healthy", cpu: 54, memory: 71, connections: ["pod-5", "pod-6", "pod-7"], x: 400, y: 220 },
  { id: "node-3", name: "aks-nodepool1-vm2", type: "node", status: "warning", cpu: 91, memory: 88, connections: ["pod-8", "pod-9", "pod-10"], x: 600, y: 220 },
  { id: "pod-1", name: "web-app-7d4f", type: "pod", status: "healthy", cpu: 34, memory: 45, connections: ["svc-web"], x: 100, y: 380 },
  { id: "pod-2", name: "web-app-8e5g", type: "pod", status: "healthy", cpu: 28, memory: 41, connections: ["svc-web"], x: 180, y: 380 },
  { id: "pod-3", name: "api-gateway-a1b2", type: "pod", status: "healthy", cpu: 67, memory: 58, connections: ["svc-api"], x: 260, y: 380 },
  { id: "pod-4", name: "api-gateway-c3d4", type: "pod", status: "healthy", cpu: 72, memory: 62, connections: ["svc-api"], x: 340, y: 380 },
  { id: "pod-5", name: "auth-service-e5f6", type: "pod", status: "healthy", cpu: 45, memory: 52, connections: ["svc-auth"], x: 420, y: 380 },
  { id: "pod-6", name: "payments-g7h8", type: "pod", status: "warning", cpu: 89, memory: 84, connections: ["svc-pay"], x: 500, y: 380 },
  { id: "pod-7", name: "payments-i9j0", type: "pod", status: "healthy", cpu: 56, memory: 48, connections: ["svc-pay"], x: 580, y: 380 },
  { id: "pod-8", name: "ml-pipeline-k1l2", type: "pod", status: "healthy", cpu: 92, memory: 76, connections: ["svc-ml"], x: 660, y: 380 },
  { id: "pod-9", name: "notif-svc-m3n4", type: "pod", status: "critical", cpu: 12, memory: 95, connections: ["svc-notif"], x: 740, y: 380 },
  { id: "pod-10", name: "cache-redis-o5p6", type: "pod", status: "healthy", cpu: 22, memory: 38, connections: [], x: 820, y: 380 },
  { id: "svc-web", name: "web-app-svc", type: "service", status: "healthy", cpu: 0, memory: 0, connections: ["svc-api"], x: 140, y: 500 },
  { id: "svc-api", name: "api-gateway-svc", type: "service", status: "healthy", cpu: 0, memory: 0, connections: ["svc-auth", "svc-pay", "svc-ml", "svc-notif"], x: 300, y: 500 },
  { id: "svc-auth", name: "auth-service-svc", type: "service", status: "healthy", cpu: 0, memory: 0, connections: [], x: 460, y: 500 },
  { id: "svc-pay", name: "payments-svc", type: "service", status: "warning", cpu: 0, memory: 0, connections: [], x: 540, y: 500 },
  { id: "svc-ml", name: "ml-pipeline-svc", type: "service", status: "healthy", cpu: 0, memory: 0, connections: [], x: 660, y: 500 },
  { id: "svc-notif", name: "notification-svc", type: "service", status: "critical", cpu: 0, memory: 0, connections: [], x: 740, y: 500 },
];

import { useNotifications } from "@/lib/NotificationContext";
import { LockedView } from "@/components/dashboard/LockedView";

const statusColor = (status: string) => {
  switch (status) { case "healthy": return { fill: "#22c55e", stroke: "#22c55e40", glow: "0 0 12px #22c55e40" }; case "warning": return { fill: "#f59e0b", stroke: "#f59e0b40", glow: "0 0 12px #f59e0b40" }; default: return { fill: "#ef4444", stroke: "#ef444440", glow: "0 0 12px #ef444440" }; }
};

export default function InfrastructurePage() {
  const { hasDeployed } = useNotifications();

  if (!hasDeployed) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Infrastructure Topology</h1>
          <p className="text-foreground-muted text-sm mt-1">Live Kubernetes cluster visualization</p>
        </div>
        <LockedView featureName="Infrastructure Topology" />
      </div>
    );
  }

  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const hovered = infraNodes.find(n => n.id === hoveredId);

  const clusters = infraNodes.filter(n => n.type === "cluster");
  const nodes = infraNodes.filter(n => n.type === "node");
  const pods = infraNodes.filter(n => n.type === "pod");
  const services = infraNodes.filter(n => n.type === "service");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-bold">Infrastructure Topology</h1><p className="text-foreground-muted text-sm mt-1">Live Kubernetes cluster visualization</p></div>
        <div className="flex items-center gap-2">
          <button onClick={() => setZoom(z => Math.max(0.5, z - 0.1))} className="glass-subtle px-3 py-1.5 rounded-lg text-sm">−</button>
          <span className="text-xs text-foreground-muted w-12 text-center">{Math.round(zoom * 100)}%</span>
          <button onClick={() => setZoom(z => Math.min(1.5, z + 0.1))} className="glass-subtle px-3 py-1.5 rounded-lg text-sm">+</button>
        </div>
      </div>

      <div className="grid lg:grid-cols-4 gap-4">
        {/* Topology */}
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="lg:col-span-3 glass rounded-xl p-6 overflow-auto relative" style={{ minHeight: 560 }}>
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
                <rect x={50} y={40} width={800} height={490} rx={16} fill="none" stroke="hsla(217,91%,60%,0.08)" strokeWidth="1" strokeDasharray="8 4" />
                <text x={60} y={30} fill="hsla(217,91%,60%,0.5)" fontSize="11" fontFamily="monospace">{c.name}</text>
              </g>
            ))}

            {/* Nodes */}
            {nodes.map(n => {
              const colors = statusColor(n.status);
              return (
                <g key={n.id} onMouseEnter={() => setHoveredId(n.id)} onMouseLeave={() => setHoveredId(null)} className="cursor-pointer">
                  <circle cx={n.x} cy={n.y} r={30} fill="hsla(228,15%,8%,0.8)" stroke={colors.stroke} strokeWidth="1.5" style={{ filter: colors.glow }} />
                  <circle cx={n.x} cy={n.y} r={8} fill={colors.fill} opacity={0.6} />
                  <text x={n.x} y={n.y + 45} textAnchor="middle" fill="hsla(210,20%,70%,0.7)" fontSize="9" fontFamily="monospace">{n.name.split("-").slice(-1)[0]}</text>
                </g>
              );
            })}

            {/* Pods */}
            {pods.map((p, i) => {
              const colors = statusColor(p.status);
              return (
                <motion.g key={p.id} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: i * 0.03 }}
                  onMouseEnter={() => setHoveredId(p.id)} onMouseLeave={() => setHoveredId(null)} className="cursor-pointer">
                  <circle cx={p.x} cy={p.y} r={14} fill="hsla(228,15%,8%,0.6)" stroke={colors.stroke} strokeWidth="1" />
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
                  <polygon points={`${s.x},${s.y - 16} ${s.x + 16},${s.y} ${s.x},${s.y + 16} ${s.x - 16},${s.y}`} fill="hsla(228,15%,8%,0.6)" stroke={colors.stroke} strokeWidth="1" />
                  <circle cx={s.x} cy={s.y} r={4} fill={colors.fill} />
                  <text x={s.x} y={s.y + 28} textAnchor="middle" fill="hsla(210,20%,70%,0.6)" fontSize="8" fontFamily="monospace">{s.name.split("-")[0]}</text>
                </g>
              );
            })}
          </svg>

          {/* Hover tooltip */}
          {hovered && (
            <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
              className="absolute glass rounded-xl p-4 z-20 w-52 pointer-events-none" style={{ left: Math.min(hovered.x + 20, 700), top: Math.min(hovered.y + 20, 480) }}>
              <p className="text-sm font-semibold text-foreground mb-1">{hovered.name}</p>
              <p className="text-xs text-foreground-muted capitalize mb-2">{hovered.type}</p>
              <div className="flex items-center gap-2 mb-1"><span className={`w-2 h-2 rounded-full ${hovered.status === "healthy" ? "bg-success" : hovered.status === "warning" ? "bg-warning" : "bg-danger"}`} /><span className="text-xs capitalize">{hovered.status}</span></div>
              {hovered.cpu > 0 && <div className="text-xs text-foreground-muted">CPU: {hovered.cpu}% • Memory: {hovered.memory}%</div>}
            </motion.div>
          )}
        </motion.div>

        {/* Stats sidebar */}
        <div className="space-y-4">
          {[{ label: "Nodes", value: nodes.length, icon: Server, color: "text-primary" }, { label: "Pods", value: pods.length, icon: Box, color: "text-success" }, { label: "Services", value: services.length, icon: Hexagon, color: "text-accent" }, { label: "Healthy", value: infraNodes.filter(n => n.status === "healthy").length, icon: Activity, color: "text-success" }].map((s, i) => (
            <motion.div key={s.label} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.1 }} className="glass rounded-xl p-4 flex items-center gap-3">
              <s.icon size={20} className={s.color} />
              <div><p className="text-2xl font-bold text-foreground">{s.value}</p><p className="text-xs text-foreground-muted">{s.label}</p></div>
            </motion.div>
          ))}

          {/* Legend */}
          <div className="glass rounded-xl p-4">
            <h4 className="text-xs font-semibold text-foreground-muted mb-3">LEGEND</h4>
            {[{ shape: "●", label: "Node", size: "30px" }, { shape: "●", label: "Pod", size: "14px" }, { shape: "◆", label: "Service", size: "20px" }].map(l => (
              <div key={l.label} className="flex items-center gap-2 text-xs text-foreground-muted mb-1"><span className="text-primary">{l.shape}</span>{l.label}</div>
            ))}
            <hr className="border-border my-2" />
            {[{ color: "bg-success", label: "Healthy" }, { color: "bg-warning", label: "Warning" }, { color: "bg-danger", label: "Critical" }].map(s => (
              <div key={s.label} className="flex items-center gap-2 text-xs text-foreground-muted mb-1"><div className={`w-2.5 h-2.5 rounded-full ${s.color}`} />{s.label}</div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
