"use client";

import { motion } from "framer-motion";
import { useState, useEffect } from "react";
import { Eye, EyeOff, Shield, RefreshCw, Key, Link2, Bell, Activity, Loader2, Sparkles, Brain, Zap, Heart } from "lucide-react";
import { useNotifications } from "@/lib/NotificationContext";
import { api } from "@/lib/api";

export default function SettingsPage() {
  const { addToast, addNotification, resetOnboarding } = useNotifications();
  const [apiKeyVisible, setApiKeyVisible] = useState(false);
  const [copied, setCopied] = useState(false);
  const [apiKey, setApiKey] = useState("");
  
  const [sysHealth, setSysHealth] = useState<any>(null);
  const [dbHealth, setDbHealth] = useState<any>(null);
  const [ghHealth, setGhHealth] = useState<any>(null);
  const [depHealth, setDepHealth] = useState<any>(null);
  const [loadingHealth, setLoadingHealth] = useState(true);

  const refreshHealthChecks = async () => {
    setLoadingHealth(true);
    try {
      const [sys, db, gh, dep] = await Promise.allSettled([
        api.getHealth(),
        api.getHealthDatabase(),
        api.getHealthGithub(),
        api.getHealthDeployments(),
      ]);
      if (sys.status === "fulfilled") setSysHealth(sys.value);
      if (db.status === "fulfilled") setDbHealth(db.value);
      if (gh.status === "fulfilled") setGhHealth(gh.value);
      if (dep.status === "fulfilled") setDepHealth(dep.value);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingHealth(false);
    }
  };

  useEffect(() => {
    refreshHealthChecks();
  }, []);
  
  const [settings, setSettings] = useState({
    predictiveScaling: true,
    autoRollback: true,
    aiThreatMitigation: true,
    autoOOMRestart: true,
    slackNotifications: false,
    emailAlerts: true,
  });

  useEffect(() => {
    async function loadSettings() {
      try {
        const data = await api.getSettings();
        setSettings({
          predictiveScaling: data.predictive_scaling,
          autoRollback: data.auto_rollback,
          aiThreatMitigation: data.ai_threat_mitigation,
          autoOOMRestart: data.auto_oom_restart,
          slackNotifications: data.slack_notifications,
          emailAlerts: data.email_alerts,
        });
      } catch (err) {
        console.error("Failed to load settings", err);
      }
    }
    loadSettings();
  }, []);

  const handleToggle = async (key: keyof typeof settings) => {
    const nextValue = !settings[key];
    const names: Record<string, string> = {
      predictiveScaling: "Auto-Scaling",
      autoRollback: "Auto-Rollback",
      aiThreatMitigation: "Threat Protection",
      autoOOMRestart: "Self-Healing",
      slackNotifications: "Slack Alerts Integration",
      emailAlerts: "Critical Incident Emails",
    };
    const title = names[key] || key;

    // Optimistically update UI
    setSettings(prev => ({ ...prev, [key]: nextValue }));

    try {
      const snakeKey = {
        predictiveScaling: "predictive_scaling",
        autoRollback: "auto_rollback",
        aiThreatMitigation: "ai_threat_mitigation",
        autoOOMRestart: "auto_oom_restart",
        slackNotifications: "slack_notifications",
        emailAlerts: "email_alerts",
      }[key];

      await api.updateSettings({
        [snakeKey]: nextValue
      });

      addToast(`${title} has been ${nextValue ? "enabled" : "disabled"}.`, nextValue ? "success" : "warning");
      
      addNotification({
        title: "Settings Updated",
        message: `${title} is now ${nextValue ? "active" : "inactive"}.`,
        type: nextValue ? "info" : "warning",
        category: "system",
        action_url: null
      });
    } catch (err) {
      // Revert on error
      setSettings(prev => ({ ...prev, [key]: !nextValue }));
      addToast(`Failed to update ${title}`, "error");
    }
  };

  const copyApiKey = () => {
    navigator.clipboard.writeText(apiKey);
    setCopied(true);
    addToast("Access token copied to clipboard!", "success");
    setTimeout(() => setCopied(false), 2000);
  };

  const regenerateApiKey = async () => {
    try {
      const data = await api.regenerateApiKey();
      setApiKey(data.apiKey);
      addToast("Regenerated CLI access token.", "success");
      addNotification({
        title: "Security Token Rotated",
        message: "A new CLI access token has been generated. Old tokens are now revoked.",
        type: "warning",
        category: "security",
        action_url: null
      });
} catch (err) {
      addToast("Failed to regenerate access key", "error");
    }
  };

  useEffect(() => {
    async function loadApiKey() {
      try {
        const data = await api.getApiKey();
        setApiKey(data.apiKey);
      } catch (err) {
        console.error("Failed to load API key", err);
        setApiKey("");
      }
    }
    loadApiKey();
  }, []);

  return (
    <div className="space-y-6">
      {/* AI Managed Infrastructure Banner */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass rounded-2xl border border-primary/20 bg-gradient-to-r from-primary/5 via-accent/5 to-transparent p-6 shadow-lg"
      >
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
            <Brain size={22} className="text-primary" />
          </div>
          <div>
            <h2 className="text-base font-bold text-foreground">AI Managed Infrastructure</h2>
            <p className="text-xs text-foreground-muted">
              ZeroOps automatically manages scaling, security, recovery, and performance optimization for your applications.
            </p>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
          {[
            { icon: Zap, label: "Auto-Scaling", active: settings.predictiveScaling },
            { icon: RefreshCw, label: "Auto-Rollback", active: settings.autoRollback },
            { icon: Shield, label: "Threat Protection", active: settings.aiThreatMitigation },
            { icon: Heart, label: "Self-Healing", active: settings.autoOOMRestart },
          ].map((item) => (
            <div key={item.label} className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-semibold transition ${
              item.active 
                ? "bg-success/10 border-success/20 text-success" 
                : "bg-card/40 border-border/40 text-foreground-muted"
            }`}>
              <item.icon size={14} />
              <span>{item.label}</span>
              <span className="ml-auto text-[9px] uppercase tracking-wider">
                {item.active ? "Active" : "Off"}
              </span>
            </div>
          ))}
        </div>
      </motion.div>

      <div className="grid md:grid-cols-3 gap-6">
        {/* Left Column: AI Managed Features */}
        <div className="md:col-span-2 space-y-6">
          {/* AI Managed Features (formerly AI Autonomic Settings) */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-card border border-border rounded-xl p-6 shadow-sm"
          >
            <h3 className="font-bold text-base text-foreground mb-2 flex items-center gap-2">
              <Sparkles size={18} className="text-primary" />
              AI Managed Features
            </h3>
            <p className="text-xs text-foreground-muted mb-6">
              These features are managed by AI automatically. You can override them if needed.
            </p>

            <div className="space-y-3">
              {[
                {
                  key: "predictiveScaling" as const,
                  title: "Auto-Scaling",
                  desc: "Automatically scales your app when traffic increases or decreases.",
                },
                {
                  key: "autoRollback" as const,
                  title: "Auto-Rollback",
                  desc: "Returns to the working version if a deployment fails health checks.",
                },
                {
                  key: "aiThreatMitigation" as const,
                  title: "Threat Protection",
                  desc: "Blocks malicious traffic and DDoS attempts automatically.",
                },
                {
                  key: "autoOOMRestart" as const,
                  title: "Self-Healing",
                  desc: "Detects crashes and restarts your app with optimized settings.",
                },
              ].map((item) => (
                <div key={item.key} className="flex items-center justify-between p-4 rounded-lg bg-background-secondary/50 hover:bg-card-hover/40 transition border border-border/40">
                  <div className="space-y-0.5 pr-6">
                    <p className="text-xs font-bold text-foreground flex items-center gap-1.5">
                      {item.title}
                      {settings[item.key] && (
                        <span className="text-[8px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary font-bold uppercase tracking-wider">
                          AI Managed
                        </span>
                      )}
                    </p>
                    <p className="text-[10px] text-foreground-muted leading-relaxed">{item.desc}</p>
                  </div>
                  <button
                    onClick={() => handleToggle(item.key)}
                    className={`w-10 h-5.5 rounded-full transition-all duration-200 relative cursor-pointer flex-shrink-0 ${settings[item.key] ? "bg-primary" : "bg-card-hover border border-border"}`}
                  >
                    <div
                      className={`w-3.5 h-3.5 rounded-full bg-white absolute top-0.5 transition-all duration-200 ${settings[item.key] ? "right-1" : "left-1"}`}
                    />
                  </button>
                </div>
              ))}
            </div>
          </motion.div>

          {/* Cloud Integrations status */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="bg-card border border-border rounded-xl p-6 shadow-sm"
          >
            <h3 className="font-bold text-base text-foreground mb-4 flex items-center gap-2">
              <Link2 size={18} className="text-primary" />
              Connected Integrations
            </h3>
            
            <div className="space-y-2.5">
              {[
                { name: "GitHub", details: "Connected to your GitHub account", status: "active", icon: "🐙" },
                { name: "Microsoft Azure", details: "Cloud hosting and deployment platform", status: "active", icon: "☁️" },
                { name: "Slack Notifications", details: "Get notified about deployments and incidents", status: "inactive", icon: "💬" }
              ].map((prov) => (
                <div key={prov.name} className="flex items-center justify-between p-3 rounded-lg bg-background-secondary/40 border border-border/40">
                  <div className="flex items-center gap-3">
                    <span className="text-xl">{prov.icon}</span>
                    <div>
                      <p className="text-xs font-bold text-foreground">{prov.name}</p>
                      <p className="text-[10px] text-foreground-muted">{prov.details}</p>
                    </div>
                  </div>
                  <span className={`text-[9px] px-2 py-0.5 rounded-full font-bold ${prov.status === "active" ? "bg-success/15 text-success" : "bg-foreground-muted/10 text-foreground-muted"}`}>
                    {prov.status === "active" ? "Connected" : "Not Configured"}
                  </span>
                </div>
              ))}
            </div>
          </motion.div>

          {/* Developer Sandbox / Onboarding Reset */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="bg-card border border-warning/30 rounded-xl p-6 shadow-sm"
          >
            <h3 className="font-bold text-base mb-2 flex items-center gap-2 text-warning">
              <RefreshCw size={18} className="text-warning" />
              Developer Sandbox Tools
            </h3>
            <p className="text-xs text-foreground-muted mb-6">
              Reset the local state to re-test the onboarding wizard and deployment pipeline.
            </p>

            <button
              onClick={() => {
                resetOnboarding();
                addToast("Onboarding state reset successfully! Redirecting...", "success");
                setTimeout(() => {
                  window.location.href = "/dashboard";
                }, 1000);
              }}
              className="px-4 py-2 bg-warning hover:bg-warning/85 text-black rounded-lg text-xs font-bold transition cursor-pointer shadow-sm"
            >
              Reset Onboarding State
            </button>
          </motion.div>

          {/* Admin Diagnostics & Health Checks */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.12 }}
            className="bg-card border border-border rounded-xl p-6 shadow-sm"
          >
            <h3 className="font-bold text-base mb-2 flex items-center gap-2 text-foreground">
              <Activity className="text-primary" size={18} />
              System Health
            </h3>
            <p className="text-xs text-foreground-muted mb-6">
              Live status checks for connected services and infrastructure.
            </p>

            <div className="space-y-3">
              {[
                { name: "System Core", status: sysHealth?.status === "healthy" ? "healthy" : "unhealthy", details: `Env: ${sysHealth?.environment || "production"}`, loading: loadingHealth },
                { name: "Database", status: dbHealth?.status === "healthy" ? "healthy" : "unhealthy", details: dbHealth?.details || "Not reachable", loading: loadingHealth },
                { name: "GitHub", status: ghHealth?.status === "healthy" ? "healthy" : "unhealthy", details: ghHealth?.details || "Not reachable", loading: loadingHealth },
                { name: "Deployment Engine", status: depHealth?.status === "healthy" ? "healthy" : "unhealthy", details: `Total runs: ${depHealth?.total_deployments ?? 0} (${depHealth?.active_deployments_running ?? 0} active)`, loading: loadingHealth },
              ].map((service) => (
                <div key={service.name} className="flex items-center justify-between p-3 rounded-lg bg-background-secondary/40 border border-border/40">
                  <div>
                    <p className="text-xs font-bold text-foreground">{service.name}</p>
                    <p className="text-[10px] text-foreground-muted">{service.details}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {service.loading ? (
                      <Loader2 size={12} className="animate-spin text-foreground-muted" />
                    ) : (
                      <>
                        <div className={`w-2.5 h-2.5 rounded-full ${service.status === "healthy" ? "bg-success animate-pulse" : "bg-danger"}`} />
                        <span className={`text-[10px] font-bold ${service.status === "healthy" ? "text-success" : "text-danger"}`}>
                          {service.status === "healthy" ? "Online" : "Offline"}
                        </span>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
            
            <button
              onClick={refreshHealthChecks}
              className="mt-4 px-4 py-2 bg-background-secondary border border-border hover:bg-card-hover text-foreground text-xs font-bold rounded-lg transition cursor-pointer shadow-sm"
            >
              Refresh
            </button>
          </motion.div>
        </div>

        {/* Right Column: API Keys + Alerts */}
        <div className="space-y-6">
          {/* API Keys */}
          <motion.div
            initial={{ opacity: 0, x: 15 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.1 }}
            className="bg-card border border-border rounded-xl p-5 shadow-sm"
          >
            <h3 className="font-bold text-sm mb-2 flex items-center gap-2 text-foreground">
              <Key size={14} className="text-primary" />
              CLI Access Tokens
            </h3>
            <p className="text-[10px] text-foreground-muted mb-4 leading-normal">
              Use this key to authorize the ZeroOps CLI in your terminal.
            </p>

            <div className="space-y-3">
              <div className="flex gap-2">
                <div className="flex-1 bg-background-secondary border border-border rounded-lg px-3 py-2 flex items-center justify-between min-w-0">
                  <span className="font-mono text-xs truncate select-none text-foreground-muted">
                    {apiKeyVisible ? apiKey : "••••••••••••••••••••••••••••••••••••"}
                  </span>
                  <button
                    onClick={() => setApiKeyVisible(!apiKeyVisible)}
                    className="text-foreground-muted hover:text-foreground p-0.5 ml-2 flex-shrink-0 cursor-pointer"
                  >
                    {apiKeyVisible ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
                <button
                  onClick={copyApiKey}
                  className="px-3 bg-primary hover:bg-primary-hover text-white text-xs font-bold rounded-lg transition cursor-pointer shadow-sm"
                >
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
              
              <button 
                onClick={regenerateApiKey}
                className="w-full py-2 bg-background-secondary border border-border hover:bg-card-hover text-foreground text-xs font-bold rounded-lg transition flex items-center justify-center gap-1.5 cursor-pointer shadow-sm"
              >
                <RefreshCw size={12} />
                Regenerate Access Key
              </button>
            </div>
          </motion.div>

          {/* System Notifications */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            className="bg-card border border-border rounded-xl p-5 shadow-sm"
          >
            <h3 className="font-bold text-sm mb-3 flex items-center gap-2 text-foreground">
              <Bell size={14} className="text-primary" />
              Notifications
            </h3>
            
            <div className="space-y-3 text-xs">
              {[
                { key: "emailAlerts" as const, label: "Email Alerts", desc: "Get notified about outages and critical issues" },
                { key: "slackNotifications" as const, label: "Slack Digests", desc: "Weekly AI optimization summaries" }
              ].map((alert) => (
                <div key={alert.key} className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-bold text-foreground">{alert.label}</p>
                    <p className="text-[10px] text-foreground-muted mt-0.5">{alert.desc}</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={settings[alert.key]}
                    onChange={() => handleToggle(alert.key)}
                    className="w-4 h-4 rounded border-border text-primary focus:ring-primary bg-card mt-0.5 cursor-pointer"
                  />
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
