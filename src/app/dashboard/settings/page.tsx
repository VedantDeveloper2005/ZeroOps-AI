"use client";

import { motion } from "framer-motion";
import { useState, useEffect } from "react";
import {
  Eye, EyeOff, Shield, RefreshCw, Key, Globe, Bell, Activity,
  Loader2, Sparkles, Brain, Zap, Heart, Settings, Users, Mail,
  CheckCircle, Plus, Info, ShieldAlert, Trash2
} from "lucide-react";
import { useNotifications } from "@/lib/NotificationContext";
import { api } from "@/lib/api";

type TabId = "general" | "domains" | "security" | "team" | "notifications" | "ai";

export default function SettingsPage() {
  const { addToast, addNotification, resetOnboarding } = useNotifications();
  const [activeTab, setActiveTab] = useState<TabId>("general");

  // API Key state
  const [apiKeyVisible, setApiKeyVisible] = useState(false);
  const [copied, setCopied] = useState(false);
  const [apiKey, setApiKey] = useState("");

  // Health check states
  const [sysHealth, setSysHealth] = useState<any>(null);
  const [dbHealth, setDbHealth] = useState<any>(null);
  const [ghHealth, setGhHealth] = useState<any>(null);
  const [depHealth, setDepHealth] = useState<any>(null);
  const [loadingHealth, setLoadingHealth] = useState(true);

  // General settings form state
  const [projName, setProjName] = useState("ZeroOps AI Application");
  const [projDesc, setProjDesc] = useState("World-class autonomous deployment platform running on Microsoft Azure AKS.");

  // Domain state
  const [domains, setDomains] = useState([
    { name: "zeroops-app.zeroops.app", default: true, ssl: true },
    { name: "zeroops.ai", default: false, ssl: true }
  ]);
  const [newDomain, setNewDomain] = useState("");

  // Secrets state
  const [secrets, setSecrets] = useState([
    { key: "DATABASE_URL", value: "postgresql://zeroops_user:••••••••••••@db.zeroops.azure.com:5432/production" },
    { key: "JWT_SECRET", value: "zo_jwt_sec_84b72fd91c28c83e1a0b5a37f59b6c2d" }
  ]);

  // System settings state
  const [settings, setSettings] = useState({
    predictiveScaling: true,
    autoRollback: true,
    aiThreatMitigation: true,
    autoOOMRestart: true,
    slackNotifications: false,
    emailAlerts: true,
  });

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
    } catch (err) {
      addToast("Failed to regenerate access key", "error");
    }
  };

  const handleAddDomain = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDomain.trim()) return;
    setDomains([...domains, { name: newDomain, default: false, ssl: true }]);
    addToast(`Domain ${newDomain} connected. SSL generated automatically.`, "success");
    setNewDomain("");
  };

  const tabs = [
    { id: "general" as const, label: "General", icon: Settings },
    { id: "domains" as const, label: "Domains", icon: Globe },
    { id: "security" as const, label: "Security & Secrets", icon: Shield },
    { id: "team" as const, label: "Team Access", icon: Users },
    { id: "notifications" as const, label: "Notifications", icon: Bell },
    { id: "ai" as const, label: "AI Settings", icon: Brain }
  ];

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-12">
      {/* Settings layout headers */}
      <div className="border-b border-border/40 pb-5">
        <h1 className="text-2xl font-extrabold tracking-tight text-foreground">Project Settings</h1>
        <p className="text-xs text-foreground-muted">Configure domains, environment variables, security credentials, and AI settings.</p>
      </div>

      <div className="grid md:grid-cols-4 gap-6">
        {/* Tab Selection menu */}
        <div className="flex flex-row md:flex-col overflow-x-auto no-scrollbar md:space-y-1 gap-1 pb-2 md:pb-0 border-b border-border/20 md:border-b-0">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2.5 px-3 py-2 text-xs font-semibold rounded-xl transition cursor-pointer whitespace-nowrap ${
                  isActive
                    ? "bg-primary/10 text-primary border border-primary/20"
                    : "text-foreground-muted hover:text-foreground hover:bg-card-hover border border-transparent"
                }`}
              >
                <Icon size={14} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Tab Contents */}
        <div className="md:col-span-3 min-h-[400px]">
          {/* GENERAL TAB */}
          {activeTab === "general" && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
              <div className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
                <h3 className="font-extrabold text-sm text-foreground">General Configuration</h3>
                <div className="space-y-4 text-xs">
                  <div className="space-y-1.5">
                    <label className="font-bold text-foreground-muted">Project Name</label>
                    <input
                      type="text"
                      value={projName}
                      onChange={(e) => setProjName(e.target.value)}
                      className="w-full bg-background-secondary border border-border rounded-xl px-4 py-2.5 text-foreground focus:border-primary focus:outline-none font-medium"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="font-bold text-foreground-muted">Description</label>
                    <textarea
                      value={projDesc}
                      onChange={(e) => setProjDesc(e.target.value)}
                      rows={3}
                      className="w-full bg-background-secondary border border-border rounded-xl px-4 py-2.5 text-foreground focus:border-primary focus:outline-none font-medium resize-none"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="font-bold text-foreground-muted">Hosting Environment</label>
                    <div className="bg-background-secondary/40 p-3.5 rounded-xl border border-border/40 font-mono text-[10px] text-foreground-muted flex items-center justify-between">
                      <span>Azure App Service (West US cluster)</span>
                      <span className="text-[9px] bg-primary/10 border border-primary/20 text-primary px-2 py-0.2 rounded-full font-bold uppercase">Production</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Reset state box */}
              <div className="bg-card border border-warning/30 rounded-xl p-6 shadow-sm space-y-3">
                <h3 className="font-extrabold text-sm text-warning flex items-center gap-1.5">
                  <RefreshCw size={16} /> Reset Sandbox Database
                </h3>
                <p className="text-xs text-foreground-muted leading-relaxed font-medium">
                  Resetting onboarding reverts all telemetry metrics and projects back to baseline configurations.
                </p>
                <button
                  onClick={() => {
                    resetOnboarding();
                    addToast("Onboarding state reset successfully! Redirecting...", "success");
                    setTimeout(() => { window.location.href = "/dashboard"; }, 1000);
                  }}
                  className="px-4 py-2 bg-warning hover:bg-warning/85 text-black rounded-lg text-xs font-bold transition cursor-pointer shadow-sm"
                >
                  Reset Onboarding State
                </button>
              </div>
            </motion.div>
          )}

          {/* DOMAINS TAB */}
          {activeTab === "domains" && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
              <div className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
                <h3 className="font-extrabold text-sm text-foreground">Connected Domains</h3>
                <div className="space-y-3">
                  {domains.map((dom) => (
                    <div key={dom.name} className="flex items-center justify-between p-3.5 rounded-xl bg-background-secondary/30 border border-border/40 text-xs">
                      <div className="space-y-0.5">
                        <p className="font-mono font-bold text-foreground">{dom.name}</p>
                        <p className="text-[10px] text-foreground-muted font-medium">
                          {dom.default ? "System default domain" : "Custom mapped alias"}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        {dom.ssl && (
                          <span className="flex items-center gap-1 text-[9px] bg-success/10 border border-success/20 text-success px-2 py-0.5 rounded-full font-bold uppercase">
                            <CheckCircle size={10} /> SSL Active
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Add domain form */}
                <form onSubmit={handleAddDomain} className="flex gap-2 text-xs pt-2">
                  <input
                    type="text"
                    value={newDomain}
                    onChange={(e) => setNewDomain(e.target.value)}
                    placeholder="my-domain.com"
                    className="flex-1 bg-background-secondary border border-border rounded-xl px-4 py-2.5 text-foreground focus:border-primary focus:outline-none font-medium"
                  />
                  <button type="submit" className="px-4 py-2.5 bg-primary hover:bg-primary-hover text-white font-bold rounded-xl transition flex items-center gap-1 shadow-md shadow-primary/10 cursor-pointer">
                    <Plus size={14} /> Add Domain
                  </button>
                </form>
              </div>
            </motion.div>
          )}

          {/* SECURITY & SECRETS TAB */}
          {activeTab === "security" && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
              {/* Access tokens */}
              <div className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
                <h3 className="font-extrabold text-sm text-foreground flex items-center gap-1.5">
                  <Key size={16} className="text-primary" /> API Access Tokens
                </h3>
                <p className="text-xs text-foreground-muted leading-normal">
                  Use this key to authorize the ZeroOps CLI in your shell tools.
                </p>
                <div className="flex gap-2 text-xs">
                  <div className="flex-1 bg-background-secondary border border-border rounded-xl px-3.5 py-2.5 flex items-center justify-between min-w-0">
                    <span className="font-mono text-xs truncate select-none text-foreground-muted">
                      {apiKeyVisible ? apiKey : "••••••••••••••••••••••••••••••••••••"}
                    </span>
                    <button
                      onClick={() => setApiKeyVisible(!apiKeyVisible)}
                      className="text-foreground-muted hover:text-foreground p-0.5 ml-2 cursor-pointer"
                    >
                      {apiKeyVisible ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                  <button
                    onClick={copyApiKey}
                    className="px-4 bg-primary hover:bg-primary-hover text-white font-bold rounded-xl transition cursor-pointer shadow-sm"
                  >
                    {copied ? "Copied" : "Copy"}
                  </button>
                </div>
                <button
                  onClick={regenerateApiKey}
                  className="w-full py-2.5 bg-background-secondary border border-border hover:bg-card-hover text-foreground text-xs font-bold rounded-xl transition flex items-center justify-center gap-1.5 cursor-pointer shadow-sm"
                >
                  <RefreshCw size={12} /> Regenerate Access Key
                </button>
              </div>

              {/* Secrets Vault */}
              <div className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
                <h3 className="font-extrabold text-sm text-foreground">Environment Variables (Secrets)</h3>
                <p className="text-xs text-foreground-muted leading-normal">
                  Decrypted values are securely isolated in Azure Vault containers and only readable at application runtime.
                </p>
                <div className="space-y-2 text-xs">
                  {secrets.map((sec) => (
                    <div key={sec.key} className="flex items-center justify-between p-3 rounded-xl bg-background-secondary/30 border border-border/40">
                      <span className="font-mono font-bold text-foreground">{sec.key}</span>
                      <span className="font-mono text-[10px] text-foreground-muted truncate max-w-[200px]">{sec.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          )}

          {/* TEAM ACCESS TAB */}
          {activeTab === "team" && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
              <div className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
                <h3 className="font-extrabold text-sm text-foreground">Team Access</h3>
                <div className="space-y-3">
                  <div className="flex items-center justify-between p-3.5 rounded-xl bg-background-secondary/30 border border-border/40 text-xs">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold">U</div>
                      <div>
                        <p className="font-bold text-foreground">Project Owner</p>
                        <p className="text-[10px] text-foreground-muted">owner@zeroops.ai</p>
                      </div>
                    </div>
                    <span className="text-[9px] bg-primary/10 border border-primary/20 text-primary px-2 py-0.5 rounded-full font-bold uppercase">
                      Owner
                    </span>
                  </div>
                </div>

                <div className="border-t border-border/40 pt-4 space-y-2 text-xs">
                  <h4 className="font-bold text-foreground-muted">Invite Workspace Member</h4>
                  <div className="flex gap-2">
                    <input
                      type="email"
                      placeholder="member@company.com"
                      className="flex-1 bg-background-secondary border border-border rounded-xl px-4 py-2.5 text-foreground focus:border-primary focus:outline-none font-medium"
                    />
                    <button
                      onClick={() => addToast("Invitation link sent to member.", "success")}
                      className="px-4 py-2.5 bg-primary hover:bg-primary-hover text-white font-bold rounded-xl transition cursor-pointer shadow-md shadow-primary/10"
                    >
                      Invite
                    </button>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* NOTIFICATIONS TAB */}
          {activeTab === "notifications" && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
              <div className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-5">
                <h3 className="font-extrabold text-sm text-foreground">Alert Subscriptions</h3>
                <div className="space-y-4 text-xs">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-bold text-foreground">Critical Email Alerts</p>
                      <p className="text-[10px] text-foreground-muted mt-0.5">Receive immediate incident reports for OOM and connection crashes</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={settings.emailAlerts}
                      onChange={() => handleToggle("emailAlerts")}
                      className="w-4.5 h-4.5 rounded border-border text-primary focus:ring-primary bg-card cursor-pointer"
                    />
                  </div>

                  <div className="flex items-start justify-between gap-3 border-t border-border/20 pt-4">
                    <div>
                      <p className="font-bold text-foreground">Slack Digests</p>
                      <p className="text-[10px] text-foreground-muted mt-0.5">Push daily build updates and autoscaling evaluations to Slack channels</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={settings.slackNotifications}
                      onChange={() => handleToggle("slackNotifications")}
                      className="w-4.5 h-4.5 rounded border-border text-primary focus:ring-primary bg-card cursor-pointer"
                    />
                  </div>

                  <div className="flex items-start justify-between gap-3 border-t border-border/20 pt-4">
                    <div>
                      <p className="font-bold text-foreground">Discord Operations Integration</p>
                      <p className="text-[10px] text-foreground-muted mt-0.5">Log live container failures and health probe violations to Discord</p>
                    </div>
                    <input
                      type="checkbox"
                      className="w-4.5 h-4.5 rounded border-border text-primary focus:ring-primary bg-card cursor-pointer"
                    />
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* AI SETTINGS TAB */}
          {activeTab === "ai" && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
              {/* Managed infrastructure header banner */}
              <div className="glass rounded-xl border border-primary/20 bg-gradient-to-r from-primary/5 via-accent/5 to-transparent p-5 shadow-sm space-y-2">
                <h3 className="font-extrabold text-sm text-foreground flex items-center gap-1.5">
                  <Brain size={16} className="text-primary" /> AI Managed Infrastructure
                </h3>
                <p className="text-xs text-foreground-muted leading-relaxed font-medium">
                  ZeroOps autonomic controller manages replication, security bounds, recovery, and cost metrics without DevOps intervention.
                </p>
              </div>

              {/* Toggles */}
              <div className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
                <h3 className="font-bold text-sm text-foreground">Autonomic Core Parameters</h3>
                <div className="space-y-4 text-xs">
                  {/* Autoscaling */}
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-bold text-foreground flex items-center gap-1.5">
                        Auto-Scale Instances
                        {settings.predictiveScaling && (
                          <span className="text-[8px] bg-primary/10 text-primary px-1.5 py-0.2 rounded-full font-bold uppercase">Active</span>
                        )}
                      </p>
                      <p className="text-[10px] text-foreground-muted mt-0.5">Automatically scales your application when traffic loads fluctuation occurs</p>
                    </div>
                    <button
                      onClick={() => handleToggle("predictiveScaling")}
                      className={`w-10 h-5.5 rounded-full transition-all duration-200 relative cursor-pointer flex-shrink-0 ${
                        settings.predictiveScaling ? "bg-primary" : "bg-card-hover border border-border"
                      }`}
                    >
                      <div className={`w-3.5 h-3.5 rounded-full bg-white absolute top-0.5 transition-all duration-200 ${settings.predictiveScaling ? "right-1" : "left-1"}`} />
                    </button>
                  </div>

                  {/* Auto fix / rollback */}
                  <div className="flex items-start justify-between gap-3 border-t border-border/20 pt-4">
                    <div>
                      <p className="font-bold text-foreground flex items-center gap-1.5">
                        Auto-Fix Deployment Errors
                        {settings.autoRollback && (
                          <span className="text-[8px] bg-primary/10 text-primary px-1.5 py-0.2 rounded-full font-bold uppercase">Active</span>
                        )}
                      </p>
                      <p className="text-[10px] text-foreground-muted mt-0.5">Returns container environment back to the working version if a build/deploy fails liveness probes</p>
                    </div>
                    <button
                      onClick={() => handleToggle("autoRollback")}
                      className={`w-10 h-5.5 rounded-full transition-all duration-200 relative cursor-pointer flex-shrink-0 ${
                        settings.autoRollback ? "bg-primary" : "bg-card-hover border border-border"
                      }`}
                    >
                      <div className={`w-3.5 h-3.5 rounded-full bg-white absolute top-0.5 transition-all duration-200 ${settings.autoRollback ? "right-1" : "left-1"}`} />
                    </button>
                  </div>

                  {/* Self healing */}
                  <div className="flex items-start justify-between gap-3 border-t border-border/20 pt-4">
                    <div>
                      <p className="font-bold text-foreground flex items-center gap-1.5">
                        Self-Healing Pod Crashes
                        {settings.autoOOMRestart && (
                          <span className="text-[8px] bg-primary/10 text-primary px-1.5 py-0.2 rounded-full font-bold uppercase">Active</span>
                        )}
                      </p>
                      <p className="text-[10px] text-foreground-muted mt-0.5">Monitors container terminations (e.g. OOM exit 137) and restarts with corrected config profiles</p>
                    </div>
                    <button
                      onClick={() => handleToggle("autoOOMRestart")}
                      className={`w-10 h-5.5 rounded-full transition-all duration-200 relative cursor-pointer flex-shrink-0 ${
                        settings.autoOOMRestart ? "bg-primary" : "bg-card-hover border border-border"
                      }`}
                    >
                      <div className={`w-3.5 h-3.5 rounded-full bg-white absolute top-0.5 transition-all duration-200 ${settings.autoOOMRestart ? "right-1" : "left-1"}`} />
                    </button>
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}
