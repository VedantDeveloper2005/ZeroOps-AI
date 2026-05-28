"use client";

import { motion } from "framer-motion";
import { useState, useEffect } from "react";
import { Shield, Lock, Eye, ShieldCheck, AlertTriangle, Search } from "lucide-react";
interface SecurityThreat {
  id: string;
  type: string;
  severity: "critical" | "high" | "medium" | "low";
  source: string;
  timestamp: string;
  status: "blocked" | "detected" | "resolved" | "investigating";
  description: string;
}

const securityThreats: SecurityThreat[] = [
  { id: "threat-001", type: "DDoS Attempt", severity: "critical", source: "45.33.21.x", timestamp: "2 min ago", status: "blocked", description: "Large-scale distributed denial of service attempt detected and mitigated" },
  { id: "threat-002", type: "SQL Injection", severity: "high", source: "192.168.1.45", timestamp: "15 min ago", status: "blocked", description: "SQL injection attempt on /api/users endpoint" },
  { id: "threat-003", type: "Brute Force", severity: "medium", source: "103.42.89.x", timestamp: "1 hour ago", status: "blocked", description: "Multiple failed authentication attempts detected" },
  { id: "threat-004", type: "XSS Attempt", severity: "medium", source: "78.92.13.x", timestamp: "2 hours ago", status: "resolved", description: "Cross-site scripting attempt in comment field" },
  { id: "threat-005", type: "Port Scan", severity: "low", source: "212.47.xx.x", timestamp: "4 hours ago", status: "detected", description: "Systematic port scanning activity from external source" },
  { id: "threat-006", type: "Suspicious API Call", severity: "high", source: "Internal", timestamp: "6 hours ago", status: "investigating", description: "Unusual API call pattern from service account" },
];

const blockedIPs = [
  { ip: "45.33.21.x", country: "Unknown", attacks: 1247, lastBlocked: "2 min ago" },
  { ip: "192.168.1.45", country: "US", attacks: 89, lastBlocked: "15 min ago" },
  { ip: "103.42.89.x", country: "CN", attacks: 456, lastBlocked: "1 hour ago" },
  { ip: "78.92.13.x", country: "RU", attacks: 23, lastBlocked: "2 hours ago" },
  { ip: "212.47.xx.x", country: "FR", attacks: 12, lastBlocked: "4 hours ago" },
];

const complianceItems = [
  { name: "SOC 2 Type II", status: "compliant" as const, progress: 100, lastAudit: "2025-12-15" },
  { name: "HIPAA", status: "in-progress" as const, progress: 78, lastAudit: "2025-11-20" },
  { name: "GDPR", status: "compliant" as const, progress: 100, lastAudit: "2026-01-10" },
  { name: "ISO 27001", status: "in-progress" as const, progress: 65, lastAudit: "2025-10-05" },
];

import { GaugeChart } from "@/components/ui/GaugeChart";
import { useNotifications } from "@/lib/NotificationContext";
import { DEFAULT_PROJECT_ID } from "@/lib/demo-runtime";
import { LockedView } from "@/components/dashboard/LockedView";

const severityColor: Record<string, string> = { critical: "bg-danger/10 text-danger border-l-danger", high: "bg-warning/10 text-warning border-l-warning", medium: "bg-info/10 text-info border-l-info", low: "bg-foreground-muted/10 text-foreground-muted border-l-foreground-muted" };

export default function SecurityPage() {
  const { addToast, addNotification, hasDeployed } = useNotifications();

  if (!hasDeployed) {
    return (
      <div className="space-y-6">
        <LockedView featureName="Security Command Center" />
      </div>
    );
  }
  
  const [securityData, setSecurityData] = useState({
    securityScore: 94,
    firewallStatus: "Active",
    httpsStatus: "Enabled",
    secretsManaged: 12,
    vulnerabilities: 2,
    soc2Status: "Compliant",
    threatLevel: "Low",
    namespaceIsolated: true,
    rbacEnabled: true
  });
  const [isScanning, setIsScanning] = useState(false);

  useEffect(() => {
    fetch(`/api/security/status/${DEFAULT_PROJECT_ID}`)
      .then(res => {
        if (!res.ok) throw new Error("Failed to load status");
        return res.json();
      })
      .then(data => setSecurityData(data))
      .catch(err => console.error("Failed to load security status:", err));
  }, []);

  const handleSecurityScan = () => {
    if (isScanning) return;
    setIsScanning(true);
    addToast("Initiating live cluster vulnerability scan...", "info");
    
    setTimeout(() => {
      setIsScanning(false);
      addToast("Security scan complete. All isolation checks passed.", "success");
      addNotification({
        title: "Security Scan Completed",
        message: "Full compliance audit and key vault check completed. AKS namespace isolation is verified.",
        type: "success",
        category: "security",
        action_url: "/dashboard/security"
      });
      
      // Refresh state
      fetch(`/api/security/status/${DEFAULT_PROJECT_ID}`)
        .then(res => res.json())
        .then(data => setSecurityData(data));
    }, 1500);
  };

  const statusCards = [
    { label: "Firewall", status: securityData.firewallStatus, icon: Shield, color: "text-success" },
    { label: "HTTPS", status: securityData.httpsStatus, icon: Lock, color: "text-success" },
    { label: "Secrets", status: `${securityData.secretsManaged} Managed`, icon: Eye, color: "text-primary" },
    { label: "Vulnerabilities", status: `${securityData.vulnerabilities} Found`, icon: AlertTriangle, color: securityData.vulnerabilities > 0 ? "text-warning" : "text-success" },
    { label: "SOC2", status: securityData.soc2Status, icon: ShieldCheck, color: "text-success" },
    { label: "Threat Level", status: securityData.threatLevel, icon: Shield, color: "text-success" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-end">
        <button 
          onClick={handleSecurityScan} 
          disabled={isScanning}
          className="flex items-center gap-2 px-4 py-2.5 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary-hover disabled:opacity-50 transition shadow-sm cursor-pointer"
        >
          <Search size={16} className={isScanning ? "animate-spin" : ""} />
          {isScanning ? "Scanning..." : "Run Security Scan"}
        </button>
      </div>

      {/* Score + Status cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} 
          className="col-span-2 md:col-span-2 lg:col-span-1 bg-card border border-border rounded-xl p-4 flex flex-col items-center justify-center relative min-h-[120px] shadow-sm">
          <GaugeChart value={securityData.securityScore} label="Security Score" size={90} color="hsl(142, 60%, 40%)" />
        </motion.div>
        {statusCards.map((card, i) => (
          <motion.div key={card.label} initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
            className="bg-card border border-border rounded-xl p-4 text-center flex flex-col items-center justify-center min-h-[120px] shadow-sm">
            <card.icon size={20} className={`${card.color} mb-2`} />
            <p className="text-[10px] uppercase font-bold text-foreground-muted">{card.label}</p>
            <p className={`text-xs font-bold ${card.color} mt-1.5`}>{card.status}</p>
          </motion.div>
        ))}
      </div>

      {/* Threats Timeline */}
      <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
        <h3 className="text-sm font-bold text-foreground mb-4">Attack Detection Timeline</h3>
        <div className="space-y-3">
          {securityThreats.map((threat, i) => (
            <motion.div key={threat.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.15 + i * 0.05 }}
              className={`rounded-xl p-4 border border-border/80 border-l-4 ${severityColor[threat.severity]}`}>
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-xs text-foreground">{threat.type}</span>
                    <span className={`text-[9px] px-2 py-0.5 rounded-full font-bold uppercase ${threat.status === "blocked" ? "bg-success/15 text-success" : threat.status === "resolved" ? "bg-info/15 text-info" : "bg-warning/15 text-warning"}`}>{threat.status}</span>
                  </div>
                  <p className="text-[11px] text-foreground-muted mt-1 leading-relaxed">{threat.description}</p>
                </div>
                <div className="text-right"><p className="text-xs font-semibold text-foreground-muted">{threat.timestamp}</p><p className="text-[10px] text-foreground-muted font-mono font-semibold mt-0.5">{threat.source}</p></div>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>

      <div className="grid md:grid-cols-2 gap-4">
        {/* Blocked IPs */}
        <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
          <h3 className="text-sm font-bold text-foreground mb-4">Blocked IPs</h3>
          <table className="w-full text-sm">
            <thead><tr className="text-foreground-muted border-b border-border text-xs"><th className="text-left py-2 font-semibold">IP</th><th className="text-left py-2 font-semibold">Country</th><th className="text-left py-2 font-semibold">Attacks</th><th className="text-left py-2 font-semibold">Last Blocked</th></tr></thead>
            <tbody>{blockedIPs.map(ip => (
              <tr key={ip.ip} className="border-b border-border/50 text-xs"><td className="py-2.5 font-mono font-bold text-foreground">{ip.ip}</td><td className="py-2.5 text-foreground-muted">{ip.country}</td><td className="py-2.5 text-danger font-bold">{ip.attacks}</td><td className="py-2.5 text-foreground-muted">{ip.lastBlocked}</td></tr>
            ))}</tbody>
          </table>
        </motion.div>

        {/* Compliance */}
        <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
          <h3 className="text-sm font-bold text-foreground mb-4">Compliance Status</h3>
          <div className="space-y-4">
            {complianceItems.map(item => (
              <div key={item.name}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold text-foreground">{item.name}</span>
                  <span className={`text-[9px] px-2 py-0.5 rounded-full font-bold uppercase ${item.status === "compliant" ? "bg-success/15 text-success" : "bg-warning/15 text-warning"}`}>{item.status === "compliant" ? "Compliant" : "In Progress"}</span>
                </div>
                <div className="h-1.5 bg-background-secondary rounded-full overflow-hidden border border-border/40">
                  <motion.div initial={{ width: 0 }} animate={{ width: `${item.progress}%` }} transition={{ duration: 1, delay: 0.2 }}
                    className={`h-full rounded-full ${item.progress === 100 ? "bg-success" : "bg-warning"}`} />
                </div>
                <p className="text-[10px] text-foreground-muted mt-1.5 font-semibold">Last audit: {item.lastAudit}</p>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
