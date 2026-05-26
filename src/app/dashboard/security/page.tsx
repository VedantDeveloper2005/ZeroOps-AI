"use client";

import { motion } from "framer-motion";
import { useState, useEffect } from "react";
import { Shield, Lock, Eye, ShieldCheck, AlertTriangle, Search } from "lucide-react";
import { securityThreats, blockedIPs, complianceItems } from "@/lib/mock-data";
import { GaugeChart } from "@/components/ui/GaugeChart";
import { useNotifications } from "@/lib/NotificationContext";
import { DEFAULT_PROJECT_ID } from "@/lib/demo-runtime";

const severityColor: Record<string, string> = { critical: "bg-danger/10 text-danger border-l-danger", high: "bg-warning/10 text-warning border-l-warning", medium: "bg-info/10 text-info border-l-info", low: "bg-foreground-muted/10 text-foreground-muted border-l-foreground-muted" };

export default function SecurityPage() {
  const { addToast, addNotification } = useNotifications();
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
        type: "success"
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
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-bold">Security Command Center</h1><p className="text-foreground-muted text-sm mt-1">Real-time threat detection and automated security management</p></div>
        <button 
          onClick={handleSecurityScan} 
          disabled={isScanning}
          className="flex items-center gap-2 px-4 py-2.5 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary-hover disabled:opacity-50 transition glow-blue cursor-pointer"
        >
          <Search size={16} className={isScanning ? "animate-spin" : ""} />
          {isScanning ? "Scanning..." : "Run Security Scan"}
        </button>
      </div>

      {/* Score + Status cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
        <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} 
          className="col-span-2 md:col-span-2 lg:col-span-1 glass rounded-xl p-4 flex flex-col items-center justify-center relative min-h-[120px]">
          <GaugeChart value={securityData.securityScore} label="Security Score" size={90} color="hsl(142, 76%, 45%)" />
        </motion.div>
        {statusCards.map((card, i) => (
          <motion.div key={card.label} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
            className="glass rounded-xl p-4 text-center flex flex-col items-center justify-center min-h-[120px]">
            <card.icon size={20} className={`${card.color} mb-2`} />
            <p className="text-xs text-foreground-muted">{card.label}</p>
            <p className={`text-sm font-semibold ${card.color} mt-1`}>{card.status}</p>
          </motion.div>
        ))}
      </div>

      {/* Threats Timeline */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass rounded-xl p-6">
        <h3 className="font-semibold mb-4">Attack Detection Timeline</h3>
        <div className="space-y-3">
          {securityThreats.map((threat, i) => (
            <motion.div key={threat.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 + i * 0.08 }}
              className={`rounded-xl p-4 border-l-2 ${severityColor[threat.severity]}`}>
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm text-foreground">{threat.type}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${threat.status === "blocked" ? "bg-success/10 text-success" : threat.status === "resolved" ? "bg-info/10 text-info" : "bg-warning/10 text-warning"}`}>{threat.status}</span>
                  </div>
                  <p className="text-xs text-foreground-muted mt-1">{threat.description}</p>
                </div>
                <div className="text-right"><p className="text-xs text-foreground-muted">{threat.timestamp}</p><p className="text-[10px] text-foreground-muted font-mono">{threat.source}</p></div>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>

      <div className="grid md:grid-cols-2 gap-4">
        {/* Blocked IPs */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="glass rounded-xl p-6">
          <h3 className="font-semibold mb-4">Blocked IPs</h3>
          <table className="w-full text-sm">
            <thead><tr className="text-foreground-muted border-b border-border"><th className="text-left py-2 font-medium">IP</th><th className="text-left py-2 font-medium">Country</th><th className="text-left py-2 font-medium">Attacks</th><th className="text-left py-2 font-medium">Last Blocked</th></tr></thead>
            <tbody>{blockedIPs.map(ip => (
              <tr key={ip.ip} className="border-b border-border/50"><td className="py-2 font-mono text-xs text-foreground">{ip.ip}</td><td className="py-2 text-foreground-muted">{ip.country}</td><td className="py-2 text-danger font-medium">{ip.attacks}</td><td className="py-2 text-foreground-muted">{ip.lastBlocked}</td></tr>
            ))}</tbody>
          </table>
        </motion.div>

        {/* Compliance */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="glass rounded-xl p-6">
          <h3 className="font-semibold mb-4">Compliance Status</h3>
          <div className="space-y-4">
            {complianceItems.map(item => (
              <div key={item.name}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm text-foreground">{item.name}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${item.status === "compliant" ? "bg-success/10 text-success" : "bg-warning/10 text-warning"}`}>{item.status === "compliant" ? "Compliant" : "In Progress"}</span>
                </div>
                <div className="h-1.5 bg-card rounded-full overflow-hidden">
                  <motion.div initial={{ width: 0 }} animate={{ width: `${item.progress}%` }} transition={{ duration: 1, delay: 0.5 }}
                    className={`h-full rounded-full ${item.progress === 100 ? "bg-success" : "bg-warning"}`} />
                </div>
                <p className="text-[10px] text-foreground-muted mt-1">Last audit: {item.lastAudit}</p>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
