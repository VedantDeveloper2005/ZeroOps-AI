"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle, Copy, FileText, RefreshCw, X } from "lucide-react";
import { api, type Notification } from "@/lib/api";
import { useNotifications } from "@/lib/NotificationContext";
import { LockedView } from "@/components/dashboard/LockedView";

interface Incident {
  id: string;
  title: string;
  severity: "critical" | "warning" | "resolved";
  startTime: string;
  status: "active" | "investigating" | "resolved";
  description: string;
}

const severityConfig: Record<Incident["severity"], { color: string; border: string; dot: string }> = {
  critical: { color: "text-danger", border: "border-l-danger", dot: "bg-danger" },
  warning: { color: "text-warning", border: "border-l-warning", dot: "bg-warning" },
  resolved: { color: "text-success", border: "border-l-success", dot: "bg-success" },
};

function mapNotificationToIncident(notification: Notification): Incident {
  const severity: Incident["severity"] =
    notification.type === "critical" ? "critical" : notification.read || notification.type === "success" ? "resolved" : "warning";
  const status: Incident["status"] = notification.read ? "resolved" : notification.type === "warning" ? "investigating" : "active";
  const date = new Date(notification.created_at || Date.now());

  return {
    id: notification.id,
    title: notification.title,
    severity,
    startTime: `${date.toLocaleTimeString()} ${date.toLocaleDateString()}`,
    status,
    description: notification.message,
  };
}

export default function IncidentsPage() {
  const { addToast, hasDeployed } = useNotifications();
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [reportIncident, setReportIncident] = useState<Incident | null>(null);

  useEffect(() => {
    if (!hasDeployed) {
      setLoading(false);
      return;
    }

    let active = true;
    async function loadIncidents() {
      setLoading(true);
      try {
        const notifs = await api.getNotifications("incident");
        if (active) setIncidents(notifs.map(mapNotificationToIncident));
      } catch (err) {
        console.error("Failed to load incidents", err);
        if (active) setIncidents([]);
      } finally {
        if (active) setLoading(false);
      }
    }

    void loadIncidents();
    return () => {
      active = false;
    };
  }, [hasDeployed]);

  const handleCopyReport = () => {
    if (!reportIncident) return;
    const reportText = [
      "ZEROOPS AI INCIDENT REPORT",
      "==========================",
      `Incident ID: ${reportIncident.id}`,
      `Title: ${reportIncident.title}`,
      `Severity: ${reportIncident.severity}`,
      `Status: ${reportIncident.status}`,
      `Recorded At: ${reportIncident.startTime}`,
      "",
      "SUMMARY:",
      reportIncident.description,
    ].join("\n");

    navigator.clipboard.writeText(reportText);
    addToast("Incident report copied to clipboard.", "success");
    setReportIncident(null);
  };

  if (!hasDeployed) {
    return (
      <div className="space-y-6">
        <LockedView featureName="Incident Management" />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <RefreshCw className="w-8 h-8 animate-spin text-primary" />
        <p className="text-foreground-muted text-sm font-medium">Loading incidents...</p>
      </div>
    );
  }

  const activeIncidents = incidents.filter((incident) => incident.status !== "resolved");

  return (
    <div className="space-y-6">
      {activeIncidents.length > 0 && (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="bg-card border border-border border-l-4 border-l-warning rounded-xl p-5 relative overflow-hidden shadow-sm"
        >
          <div className="absolute inset-0 bg-warning/5 pointer-events-none" />
          <div className="relative flex items-center gap-4">
            <div className="w-10 h-10 rounded-lg bg-warning/10 flex items-center justify-center shrink-0">
              <AlertTriangle size={20} className="text-warning" />
            </div>
            <div>
              <p className="text-sm font-bold text-foreground">
                {activeIncidents.length} Active Incident{activeIncidents.length > 1 ? "s" : ""}
              </p>
              <p className="text-xs text-foreground-muted mt-0.5">
                {activeIncidents.map((incident) => incident.title).join(", ")}
              </p>
            </div>
          </div>
        </motion.div>
      )}

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-card border border-border rounded-xl p-6 shadow-sm"
      >
        <h3 className="text-sm font-bold text-foreground mb-4">Incident Event Log</h3>
        <div className="space-y-3">
          {incidents.length === 0 ? (
            <div className="p-8 text-center space-y-2 bg-card/20 border border-border rounded-xl">
              <CheckCircle size={32} className="text-success mx-auto" />
              <p className="text-sm font-semibold text-foreground">No incidents recorded</p>
              <p className="text-xs text-foreground-muted">Incident notifications from the backend will appear here.</p>
            </div>
          ) : (
            incidents.map((incident, index) => {
              const config = severityConfig[incident.severity];
              return (
                <motion.div
                  key={incident.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05 }}
                  className={`rounded-xl p-4 border border-border border-l-4 ${config.border} bg-background-secondary`}
                >
                  <div className="flex items-center justify-between gap-3 mb-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={`w-2 h-2 rounded-full ${config.dot}`} />
                      <h4 className="text-xs font-bold text-foreground truncate">{incident.title}</h4>
                      <span className={`text-[9px] uppercase px-2 py-0.5 rounded-full font-bold bg-card border border-border/80 ${config.color}`}>
                        {incident.status}
                      </span>
                    </div>
                    <span className="text-[10px] text-foreground-muted font-mono font-semibold shrink-0">
                      {incident.startTime}
                    </span>
                  </div>
                  <p className="text-xs text-foreground-muted mb-3 leading-relaxed">{incident.description}</p>
                  <button
                    onClick={() => setReportIncident(incident)}
                    className="flex items-center gap-1.5 text-[10px] font-bold text-primary hover:underline cursor-pointer"
                  >
                    <FileText size={12} />
                    Create report from event
                  </button>
                </motion.div>
              );
            })
          )}
        </div>
      </motion.div>

      {reportIncident && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-card border border-border max-w-lg w-full p-6 rounded-xl shadow-2xl relative flex flex-col max-h-[90vh]"
          >
            <button
              onClick={() => setReportIncident(null)}
              className="absolute top-4 right-4 text-foreground-muted hover:text-foreground cursor-pointer transition"
            >
              <X size={16} />
            </button>

            <h3 className="text-sm font-bold text-foreground mb-1 flex items-center gap-2">
              <FileText size={18} className="text-primary" />
              Incident Report
            </h3>
            <p className="text-[10px] text-foreground-muted font-semibold uppercase tracking-wider mb-4">
              Built from recorded backend incident notification
            </p>

            <div className="flex-1 overflow-y-auto bg-background-secondary border border-border/60 rounded-lg p-4 font-mono text-[11px] text-foreground space-y-3 no-scrollbar">
              <p className="text-primary font-bold"># {reportIncident.title}</p>
              <p className="text-foreground-muted">Incident ID: {reportIncident.id}</p>
              <p className="text-foreground-muted">Severity: {reportIncident.severity}</p>
              <p className="text-foreground-muted">Status: {reportIncident.status}</p>
              <p className="text-foreground-muted">Recorded At: {reportIncident.startTime}</p>
              <div>
                <p className="text-warning font-bold">## Summary</p>
                <p className="text-foreground-muted leading-relaxed mt-1">{reportIncident.description}</p>
              </div>
            </div>

            <div className="flex gap-3 justify-end pt-4 mt-2">
              <button
                onClick={() => setReportIncident(null)}
                className="px-3.5 py-2 border border-border rounded-lg text-xs font-semibold hover:bg-background-secondary transition cursor-pointer"
              >
                Close
              </button>
              <button
                onClick={handleCopyReport}
                className="px-3.5 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-xs font-semibold transition flex items-center gap-1.5 cursor-pointer shadow-sm"
              >
                <Copy size={12} />
                Copy Report
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}
