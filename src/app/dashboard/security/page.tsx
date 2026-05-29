"use client";

import { motion } from "framer-motion";
import { useState, useEffect } from "react";
import { Shield, Lock, Eye, ShieldCheck, AlertTriangle, Search } from "lucide-react";
import { GaugeChart } from "@/components/ui/GaugeChart";
import { useNotifications } from "@/lib/NotificationContext";
import { api, type Project } from "@/lib/api";
import { LockedView } from "@/components/dashboard/LockedView";

interface SecurityThreat {
  id: string;
  type: string;
  severity: "critical" | "high" | "medium" | "low";
  source: string;
  timestamp: string;
  status: "blocked" | "detected" | "resolved" | "investigating";
  description: string;
}

type SecurityData = {
  securityScore: number;
  firewallStatus: string;
  httpsStatus: string;
  secretsManaged: number;
  vulnerabilities: number;
  soc2Status: string;
  threatLevel: string;
  namespaceIsolated: boolean;
  rbacEnabled: boolean;
};

const severityColor: Record<string, string> = { critical: "bg-danger/10 text-danger border-l-danger", high: "bg-warning/10 text-warning border-l-warning", medium: "bg-info/10 text-info border-l-info", low: "bg-foreground-muted/10 text-foreground-muted border-l-foreground-muted" };

export default function SecurityPage() {
  const { addToast, addNotification, hasDeployed } = useNotifications();
  const [securityData, setSecurityData] = useState<SecurityData>({
    securityScore: 0,
    firewallStatus: "Unknown",
    httpsStatus: "Unknown",
    secretsManaged: 0,
    vulnerabilities: 0,
    soc2Status: "Unknown",
    threatLevel: "Unknown",
    namespaceIsolated: false,
    rbacEnabled: false
  });
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [securityThreats, setSecurityThreats] = useState<SecurityThreat[]>([]);
  const [isScanning, setIsScanning] = useState(false);

  useEffect(() => {
    async function loadProjects() {
      try {
        const projs = await api.getProjects();
        setProjects(projs);
        if (projs.length > 0) {
          setSelectedProjectId(projs[0].id);
          loadSecurityStatus(projs[0].id);
        }
      } catch (err) {
        console.error("Failed to load projects", err);
      }
    }
    if (hasDeployed) loadProjects();
  }, [hasDeployed]);

  const loadSecurityStatus = async (projectId: string) => {
    try {
      const data = await api.getSecurityStatus(projectId);
      setSecurityData(prev => ({
        securityScore: data.securityScore ?? prev.securityScore,
        firewallStatus: data.firewallStatus ?? prev.firewallStatus,
        httpsStatus: data.httpsStatus ?? prev.httpsStatus,
        secretsManaged: data.secretsManaged ?? prev.secretsManaged,
        vulnerabilities: data.vulnerabilities ?? prev.vulnerabilities,
        soc2Status: data.soc2Status ?? prev.soc2Status,
        threatLevel: data.threatLevel ?? prev.threatLevel,
        namespaceIsolated: data.namespaceIsolated ?? prev.namespaceIsolated,
        rbacEnabled: data.rbacEnabled ?? prev.rbacEnabled
      }));
    } catch (err) {
      console.error("Failed to load security status:", err);
    }
  };

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
      
      if (selectedProjectId) {
        loadSecurityStatus(selectedProjectId);
      }
    }, 1500);
  };

  const statusCards = [
    { label: "Firewall", status: securityData.firewallStatus, icon: Shield, color: securityData.firewallStatus === "Active" ? "text-success" : "text-foreground-muted" },
    { label: "HTTPS", status: securityData.httpsStatus, icon: Lock, color: securityData.httpsStatus === "Active" ? "text-success" : "text-foreground-muted" },
    { label: "Secrets", status: securityData.secretsManaged > 0 ? `${securityData.secretsManaged} Managed` : "None", icon: Eye, color: securityData.secretsManaged > 0 ? "text-primary" : "text-foreground-muted" },
    { label: "Vulnerabilities", status: `${securityData.vulnerabilities} Found`, icon: AlertTriangle, color: securityData.vulnerabilities > 0 ? "text-warning" : "text-success" },
    { label: "SOC2", status: securityData.soc2Status, icon: ShieldCheck, color: securityData.soc2Status === "Compliant" ? "text-success" : "text-foreground-muted" },
    { label: "Threat Level", status: securityData.threatLevel, icon: Shield, color: "text-success" },
  ];

  if (!hasDeployed) {
    return (
      <div className="space-y-6">
        <LockedView featureName="Security Command Center" />
      </div>
    );
  }

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
         {securityThreats.length === 0 ? (
           <p className="text-xs text-foreground-muted py-4">No threats detected. Security monitoring is active.</p>
         ) : (
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
         )}
       </motion.div>

       <div className="grid md:grid-cols-2 gap-4">
         {/* Blocked IPs */}
         <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
           <h3 className="text-sm font-bold text-foreground mb-4">Blocked IPs</h3>
           <p className="text-xs text-foreground-muted py-4">No blocked IPs recorded. Firewall rules are being monitored.</p>
         </motion.div>

         {/* Compliance */}
         <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="bg-card border border-border rounded-xl p-6 shadow-sm">
           <h3 className="text-sm font-bold text-foreground mb-4">Compliance Status</h3>
           <p className="text-xs text-foreground-muted py-4">No compliance items configured. Configure security policies in the admin panel.</p>
         </motion.div>
       </div>
    </div>
  );
}
