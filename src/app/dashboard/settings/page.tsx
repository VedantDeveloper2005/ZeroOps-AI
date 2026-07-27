"use client";

import { motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import {
  Eye, EyeOff, Shield, RefreshCw, Key, Globe, Bell, Activity,
  Loader2, Brain, CheckCircle, Plus, Trash2, Globe2, ShieldCheck, Settings, Users
} from "lucide-react";
import { useNotifications } from "@/lib/NotificationContext";
import {
  api,
  getErrorMessage,
  type CustomDomain,
  type AzureConnection,
  type DeploymentHealth,
  type EnvVar,
  type HealthCheck,
  type ProjectMember,
  type SystemHealth,
} from "@/lib/api";

type TabId = "general" | "azure" | "domains" | "security" | "team" | "notifications" | "ai";

const emptyAzureForm = {
  tenant_id: "",
  subscription_id: "",
  client_id: "",
  client_secret: "",
  region: "eastus",
  resource_group: "",
  acr_login_server: "",
  app_service_plan: "",
  namespace_prefix: "",
};

export default function SettingsPage() {
  const { addToast, addNotification, resetOnboarding, projects, isLoading: loadingProjects } = useNotifications();
  const [activeTab, setActiveTab] = useState<TabId>("general");

  // Project selector states
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  // API Key state
  const [apiKeyVisible, setApiKeyVisible] = useState(false);
  const [copied, setCopied] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [apiKeyConfigured, setApiKeyConfigured] = useState(false);

  // Health check states
  const [sysHealth, setSysHealth] = useState<SystemHealth | null>(null);
  const [dbHealth, setDbHealth] = useState<HealthCheck | null>(null);
  const [ghHealth, setGhHealth] = useState<HealthCheck | null>(null);
  const [depHealth, setDepHealth] = useState<DeploymentHealth | null>(null);
  const [loadingHealth, setLoadingHealth] = useState(true);
  const [azureConnection, setAzureConnection] = useState<AzureConnection | null>(null);
  const [loadingAzure, setLoadingAzure] = useState(true);
  const [savingAzure, setSavingAzure] = useState(false);
  const [azureForm, setAzureForm] = useState(emptyAzureForm);

  // Domain states
  const [domains, setDomains] = useState<CustomDomain[]>([]);
  const [loadingDomains, setLoadingDomains] = useState(false);
  const [newDomain, setNewDomain] = useState("");
  const [verifyingDomainName, setVerifyingDomainName] = useState<string | null>(null);
  const [renewingDomainName, setRenewingDomainName] = useState<string | null>(null);

  // Secrets/Env vars state
  const [secrets, setSecrets] = useState<EnvVar[]>([]);
  const [loadingSecrets, setLoadingSecrets] = useState(false);
  const [newSecretKey, setNewSecretKey] = useState("");
  const [newSecretValue, setNewSecretValue] = useState("");
  const [newSecretIsSecret, setNewSecretIsSecret] = useState(true);
  const [savingSecret, setSavingSecret] = useState(false);

  // Team members state
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [newMemberEmail, setNewMemberEmail] = useState("");
  const [newMemberRole, setNewMemberRole] = useState("Developer");
  const [addingMember, setAddingMember] = useState(false);

  // System settings state
  const [settings, setSettings] = useState({
    predictiveScaling: true,
    autoRollback: true,
    aiThreatMitigation: true,
    autoOOMRestart: true,
    slackNotifications: false,
    emailAlerts: true,
  });

  const refreshHealthChecks = useCallback(async () => {
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
  }, []);

  // Set selected project ID when projects load
  useEffect(() => {
    if (projects.length > 0 && !selectedProjectId) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, selectedProjectId]);

  useEffect(() => {
    refreshHealthChecks();
  }, [refreshHealthChecks]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const tab = new URLSearchParams(window.location.search).get("tab");
    if (tab && ["general", "azure", "domains", "security", "team", "notifications", "ai"].includes(tab)) {
      setActiveTab(tab as TabId);
    }
  }, []);

  const loadAzureConnection = useCallback(async () => {
    setLoadingAzure(true);
    try {
      const data = await api.getAzureConnection();
      setAzureConnection(data);
      setAzureForm({
        tenant_id: data.tenant_id || "",
        subscription_id: data.subscription_id || "",
        client_id: data.client_id || "",
        client_secret: "",
        region: data.region || "eastus",
        resource_group: data.resource_group || "",
        acr_login_server: data.acr_login_server || "",
        app_service_plan: data.app_service_plan || "",
        namespace_prefix: data.namespace_prefix || "",
      });
    } catch (err) {
      console.error("Failed to load Azure connection", err);
      addToast("Failed to load Azure deployment target.", "error");
    } finally {
      setLoadingAzure(false);
    }
  }, [addToast]);

  useEffect(() => {
    loadAzureConnection();
  }, [loadAzureConnection]);

  // Load project-specific data when selected project changes
  useEffect(() => {
    if (!selectedProjectId) return;

    async function loadProjectData() {
      setLoadingDomains(true);
      setLoadingSecrets(true);
      setLoadingMembers(true);
      try {
        const [doms, envs, mems] = await Promise.allSettled([
          api.getProjectDomains(selectedProjectId!),
          api.getEnvVars(selectedProjectId!),
          api.getProjectMembers(selectedProjectId!),
        ]);

        if (doms.status === "fulfilled") setDomains(doms.value);
        if (envs.status === "fulfilled") setSecrets(envs.value);
        if (mems.status === "fulfilled") setMembers(mems.value);
      } catch (err) {
        console.error("Failed to load project configuration", err);
      } finally {
        setLoadingDomains(false);
        setLoadingSecrets(false);
        setLoadingMembers(false);
      }
    }
    loadProjectData();
  }, [selectedProjectId]);

  // Load global system settings & API key
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

    async function loadApiKey() {
      try {
        const data = await api.getApiKey();
        setApiKey(data.apiKey);
        setApiKeyConfigured(data.configured);
      } catch (err) {
        console.error("Failed to load API key", err);
      }
    }

    loadSettings();
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
    } catch {
      setSettings(prev => ({ ...prev, [key]: !nextValue }));
      addToast(`Failed to update ${title}`, "error");
    }
  };

  const copyApiKey = () => {
    if (!apiKey) return;
    navigator.clipboard.writeText(apiKey);
    setCopied(true);
    addToast("Access token copied to clipboard!", "success");
    setTimeout(() => setCopied(false), 2000);
  };

  const regenerateApiKey = async () => {
    try {
      const data = await api.regenerateApiKey();
      setApiKey(data.apiKey);
      setApiKeyConfigured(data.configured);
      addToast("Regenerated CLI access token.", "success");
    } catch {
      addToast("Failed to regenerate access key", "error");
    }
  };

  // Domain Handlers
  const handleAddDomain = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProjectId || !newDomain.trim()) return;

    try {
      const res = await api.connectDomain(selectedProjectId, newDomain.trim());
      setDomains(res);
      addToast(`Domain ${newDomain} connected successfully. Complete DNS verification to activate SSL.`, "success");
      setNewDomain("");
    } catch (err: unknown) {
      addToast(getErrorMessage(err, "Failed to connect domain"), "error");
    }
  };

  const handleVerifyDomain = async (domainName: string) => {
    if (!selectedProjectId) return;
    setVerifyingDomainName(domainName);
    try {
      const res = await api.verifyDomain(selectedProjectId, domainName);
      setDomains(res);
      addToast(`DNS Verified and SSL/HTTPS activated for ${domainName}!`, "success");
    } catch (err: unknown) {
      addToast(getErrorMessage(err, "Verification failed. Check your DNS records."), "error");
    } finally {
      setVerifyingDomainName(null);
    }
  };

  const handleRenewSSL = async (domainName: string) => {
    if (!selectedProjectId) return;
    setRenewingDomainName(domainName);
    try {
      const res = await api.renewSSL(selectedProjectId, domainName);
      setDomains(res);
      addToast(`SSL Certificate for ${domainName} successfully renewed.`, "success");
    } catch (err: unknown) {
      addToast(getErrorMessage(err, "SSL renewal failed."), "error");
    } finally {
      setRenewingDomainName(null);
    }
  };

  const handleRemoveDomain = async (domainName: string) => {
    if (!selectedProjectId) return;
    try {
      const res = await api.removeDomain(selectedProjectId, domainName);
      setDomains(res);
      addToast(`Domain ${domainName} removed.`, "warning");
    } catch (err: unknown) {
      addToast(getErrorMessage(err, "Failed to remove domain"), "error");
    }
  };

  // Environment Variable Secrets Handlers
  const handleAddSecret = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProjectId || !newSecretKey.trim() || !newSecretValue.trim()) return;
    setSavingSecret(true);

    try {
      const res = await api.addEnvVar(selectedProjectId, {
        key: newSecretKey.trim().toUpperCase(),
        value: newSecretValue.trim(),
        is_secret: newSecretIsSecret
      });
      setSecrets([...secrets, res]);
      setNewSecretKey("");
      setNewSecretValue("");
      addToast(`Environment variable ${newSecretKey} saved successfully.`, "success");
    } catch (err: unknown) {
      addToast(getErrorMessage(err, "Failed to save environment variable"), "error");
    } finally {
      setSavingSecret(false);
    }
  };

  const handleDeleteSecret = async (varId: string, keyName: string) => {
    if (!selectedProjectId) return;
    try {
      await api.deleteEnvVar(selectedProjectId, varId);
      setSecrets(secrets.filter(s => s.id !== varId));
      addToast(`Variable ${keyName} deleted from production environment.`, "warning");
    } catch (err: unknown) {
      addToast(getErrorMessage(err, "Failed to delete variable"), "error");
    }
  };

  // Team invitation Handlers
  const handleAddMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProjectId || !newMemberEmail.trim()) return;
    setAddingMember(true);

    try {
      const res = await api.addMember(selectedProjectId, newMemberEmail.trim(), newMemberRole);
      setMembers(res);
      setNewMemberEmail("");
      addToast(`Member ${newMemberEmail} added successfully to the workspace.`, "success");
    } catch (err: unknown) {
      addToast(getErrorMessage(err, "Failed to add team member"), "error");
    } finally {
      setAddingMember(false);
    }
  };

  const handleRemoveMember = async (email: string) => {
    if (!selectedProjectId) return;
    try {
      const res = await api.removeMember(selectedProjectId, email);
      setMembers(res);
      addToast(`Member ${email} removed from workspace.`, "warning");
    } catch (err: unknown) {
      addToast(getErrorMessage(err, "Failed to remove member"), "error");
    }
  };

  const handleAzureFieldChange = (field: keyof typeof azureForm, value: string) => {
    setAzureForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSaveAzureConnection = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingAzure(true);
    try {
      const updated = await api.updateAzureConnection({
        tenant_id: azureForm.tenant_id.trim(),
        subscription_id: azureForm.subscription_id.trim(),
        client_id: azureForm.client_id.trim() || undefined,
        client_secret: azureForm.client_secret.trim() || undefined,
        region: azureForm.region.trim() || "eastus",
        resource_group: azureForm.resource_group.trim() || undefined,
        acr_login_server: azureForm.acr_login_server.trim().replace(/\/+$/, "") || undefined,
        app_service_plan: azureForm.app_service_plan.trim() || undefined,
        namespace_prefix: azureForm.namespace_prefix.trim() || undefined,
      });
      setAzureConnection(updated);
      setAzureForm((prev) => ({ ...prev, client_secret: "" }));
      addToast("Azure deployment target saved.", "success");
    } catch (err: unknown) {
      addToast(getErrorMessage(err, "Failed to save Azure deployment target."), "error");
    } finally {
      setSavingAzure(false);
    }
  };

  const tabs = [
    { id: "general" as const, label: "General", icon: Settings },
    { id: "azure" as const, label: "Hosting", icon: Globe2 },
    { id: "domains" as const, label: "Domains", icon: Globe },
    { id: "security" as const, label: "Security & Secrets", icon: Shield },
    { id: "team" as const, label: "Team Access", icon: Users },
    { id: "notifications" as const, label: "Notifications", icon: Bell },
    { id: "ai" as const, label: "AI Settings", icon: Brain }
  ];

  const activeProject = projects.find(p => p.id === selectedProjectId);

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-12">
      {/* Settings layout headers */}
      <div className="border-b border-border/40 pb-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground">Project Settings</h1>
          <p className="text-xs text-foreground-muted">Configure domains, environment variables, security credentials, and AI settings.</p>
        </div>
        
        {/* Project Selector dropdown */}
        {!loadingProjects && projects.length > 0 && (
          <div className="flex items-center gap-2 bg-card border border-border px-3 py-1.5 rounded-xl shadow-sm">
            <span className="text-[10px] font-bold text-foreground-muted uppercase tracking-wider">Project:</span>
            <select
              value={selectedProjectId || ""}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              className="bg-transparent text-xs font-bold text-foreground focus:outline-none cursor-pointer border-none p-0"
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id} className="bg-card text-foreground font-semibold">
                  {p.name} ({p.framework})
                </option>
              ))}
            </select>
          </div>
        )}
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
                  {loadingProjects ? (
                    <div className="flex items-center gap-2 text-foreground-muted font-medium py-2">
                      <Loader2 size={14} className="animate-spin text-primary" /> Loading project information...
                    </div>
                  ) : activeProject ? (
                    <>
                      <div className="space-y-1.5">
                        <label className="font-bold text-foreground-muted">Project Name</label>
                        <input
                          type="text"
                          readOnly
                          value={activeProject.name}
                          className="w-full bg-background-secondary/50 border border-border rounded-xl px-4 py-2.5 text-foreground-muted font-mono text-xs focus:outline-none"
                        />
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                          <label className="font-bold text-foreground-muted">Repository</label>
                          <input
                            type="text"
                            readOnly
                            value={activeProject.full_name}
                            className="w-full bg-background-secondary/50 border border-border rounded-xl px-4 py-2.5 text-foreground-muted font-mono text-xs focus:outline-none"
                          />
                        </div>
                        <div className="space-y-1.5">
                          <label className="font-bold text-foreground-muted">Active Branch</label>
                          <input
                            type="text"
                            readOnly
                            value={activeProject.branch}
                            className="w-full bg-background-secondary/50 border border-border rounded-xl px-4 py-2.5 text-foreground-muted font-mono text-xs focus:outline-none"
                          />
                        </div>
                      </div>
                      <div className="space-y-1.5">
                        <label className="font-bold text-foreground-muted">Hosting Infrastructure</label>
                        <div className="bg-background-secondary/40 p-3.5 rounded-xl border border-border/40 font-mono text-[10px] text-foreground-muted flex items-center justify-between">
                          <span>Hosting target ({activeProject.region || "region not recorded"})</span>
                          <span className="text-[9px] bg-primary/10 border border-primary/20 text-primary px-2 py-0.2 rounded-full font-bold uppercase">
                            {activeProject.status || "status not recorded"}
                          </span>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="text-foreground-muted font-medium py-2">
                      No active projects. Go to Repository Import Flow to create one.
                    </div>
                  )}
                </div>
              </div>

              {/* Autonomic Diagnostics */}
              <div className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-extrabold text-sm text-foreground flex items-center gap-1.5">
                    <Activity size={16} className="text-primary animate-pulse" /> Autonomic Platform Diagnostics
                  </h3>
                  <button
                    onClick={refreshHealthChecks}
                    disabled={loadingHealth}
                    className="p-1.5 hover:bg-card-hover rounded-lg text-foreground-muted hover:text-foreground cursor-pointer transition border border-border/40"
                  >
                    <RefreshCw size={12} className={loadingHealth ? "animate-spin" : ""} />
                  </button>
                </div>
                
                <div className="grid grid-cols-2 gap-3 text-xs">
                  {/* System check */}
                  <div className="p-3 bg-background-secondary/30 rounded-xl border border-border/40 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-foreground-muted">AI Control Engine</span>
                      <span className={`w-2 h-2 rounded-full ${sysHealth?.status === "healthy" ? "bg-success" : "bg-warning"}`} />
                    </div>
                    <p className="text-[10px] text-foreground-muted font-mono">
                      Env: {sysHealth?.environment || "production"} <br />
                      API: {sysHealth?.openAIConfigured ? "OpenAI Connected" : "Local Engine Running"}
                    </p>
                  </div>
                  
                  {/* Database check */}
                  <div className="p-3 bg-background-secondary/30 rounded-xl border border-border/40 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-foreground-muted">Database Server</span>
                      <span className={`w-2 h-2 rounded-full ${dbHealth?.status === "healthy" ? "bg-success" : "bg-warning"}`} />
                    </div>
                    <p className="text-[10px] text-foreground-muted font-mono">
                      Type: PostgreSQL <br />
                      State: {dbHealth?.details || "Checking..."}
                    </p>
                  </div>

                  {/* GitHub check */}
                  <div className="p-3 bg-background-secondary/30 rounded-xl border border-border/40 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-foreground-muted">GitHub Sync</span>
                      <span className={`w-2 h-2 rounded-full ${ghHealth?.status === "healthy" ? "bg-success" : "bg-warning"}`} />
                    </div>
                    <p className="text-[10px] text-foreground-muted font-mono">
                      Webhook: Active <br />
                      State: {ghHealth?.details || "Checking..."}
                    </p>
                  </div>

                  {/* Orchestrator check */}
                  <div className="p-3 bg-background-secondary/30 rounded-xl border border-border/40 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-foreground-muted">Container Telemetry</span>
                      <span className={`w-2 h-2 rounded-full ${depHealth?.status === "healthy" ? "bg-success" : "bg-warning"}`} />
                    </div>
                    <p className="text-[10px] text-foreground-muted font-mono">
                      Total Deploys: {depHealth?.total_deployments || 0} <br />
                      Active Pipelines: {depHealth?.active_deployments_running || 0}
                    </p>
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

          {/* HOSTING TAB */}
          {activeTab === "azure" && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
              <div className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-5">
                <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 border-b border-border/40 pb-4">
                  <div className="space-y-1">
                    <h3 className="font-extrabold text-sm text-foreground flex items-center gap-1.5">
                      <Globe2 size={16} className="text-primary" /> Azure hosting
                    </h3>
                    <p className="text-xs text-foreground-muted leading-relaxed">
                      Connect the Azure environment where your applications will be built and published. ZeroOps keeps the infrastructure details out of your day-to-day workflow.
                    </p>
                  </div>
                  <span className={`text-[10px] px-2.5 py-1 rounded-full border font-bold uppercase w-fit ${
                    azureConnection?.connected && azureConnection.acr_login_server && azureConnection.app_service_plan
                      ? "bg-success/10 border-success/25 text-success"
                      : "bg-warning/10 border-warning/25 text-warning"
                  }`}>
                    {azureConnection?.connected && azureConnection.acr_login_server && azureConnection.app_service_plan
                      ? "Ready"
                      : "Needs Setup"}
                  </span>
                </div>

                {loadingAzure ? (
                  <div className="flex items-center gap-2 text-foreground-muted font-medium py-8 text-xs">
                    <Loader2 size={14} className="animate-spin text-primary" /> Loading Azure target...
                  </div>
                ) : (
                  <form onSubmit={handleSaveAzureConnection} className="space-y-5 text-xs">
                    <div className="grid md:grid-cols-2 gap-4">
                      <label className="space-y-1.5">
                        <span className="font-bold text-foreground-muted">Tenant ID</span>
                        <input
                          type="text"
                          required
                          value={azureForm.tenant_id}
                          onChange={(e) => handleAzureFieldChange("tenant_id", e.target.value)}
                          className="w-full bg-background-secondary border border-border rounded-xl px-4 py-2.5 text-foreground focus:border-primary focus:outline-none font-mono"
                        />
                      </label>
                      <label className="space-y-1.5">
                        <span className="font-bold text-foreground-muted">Subscription ID</span>
                        <input
                          type="text"
                          required
                          value={azureForm.subscription_id}
                          onChange={(e) => handleAzureFieldChange("subscription_id", e.target.value)}
                          className="w-full bg-background-secondary border border-border rounded-xl px-4 py-2.5 text-foreground focus:border-primary focus:outline-none font-mono"
                        />
                      </label>
                      <label className="space-y-1.5">
                        <span className="font-bold text-foreground-muted">Client ID</span>
                        <input
                          type="text"
                          value={azureForm.client_id}
                          onChange={(e) => handleAzureFieldChange("client_id", e.target.value)}
                          className="w-full bg-background-secondary border border-border rounded-xl px-4 py-2.5 text-foreground focus:border-primary focus:outline-none font-mono"
                        />
                      </label>
                      <label className="space-y-1.5">
                        <span className="font-bold text-foreground-muted">Client Secret</span>
                        <input
                          type="password"
                          value={azureForm.client_secret}
                          onChange={(e) => handleAzureFieldChange("client_secret", e.target.value)}
                          placeholder={azureConnection?.connected ? "Leave blank to keep existing" : "Required to verify this connection"}
                          className="w-full bg-background-secondary border border-border rounded-xl px-4 py-2.5 text-foreground placeholder:text-foreground-muted focus:border-primary focus:outline-none font-mono"
                        />
                      </label>
                      <label className="space-y-1.5">
                        <span className="font-bold text-foreground-muted">Region</span>
                        <input
                          type="text"
                          value={azureForm.region}
                          onChange={(e) => handleAzureFieldChange("region", e.target.value)}
                          className="w-full bg-background-secondary border border-border rounded-xl px-4 py-2.5 text-foreground focus:border-primary focus:outline-none font-mono"
                        />
                      </label>
                      <label className="space-y-1.5">
                        <span className="font-bold text-foreground-muted">Resource Group</span>
                        <input
                          type="text"
                          value={azureForm.resource_group}
                          onChange={(e) => handleAzureFieldChange("resource_group", e.target.value)}
                          className="w-full bg-background-secondary border border-border rounded-xl px-4 py-2.5 text-foreground focus:border-primary focus:outline-none font-mono"
                        />
                      </label>
                      <label className="space-y-1.5">
                        <span className="font-bold text-foreground-muted">ACR Login Server</span>
                        <input
                          type="text"
                          required
                          value={azureForm.acr_login_server}
                          onChange={(e) => handleAzureFieldChange("acr_login_server", e.target.value)}
                          placeholder="myregistry.azurecr.io"
                          className="w-full bg-background-secondary border border-border rounded-xl px-4 py-2.5 text-foreground placeholder:text-foreground-muted focus:border-primary focus:outline-none font-mono"
                        />
                      </label>
                      <label className="space-y-1.5">
                        <span className="font-bold text-foreground-muted">Linux App Service plan</span>
                        <input
                          type="text"
                          required
                          value={azureForm.app_service_plan}
                          onChange={(e) => handleAzureFieldChange("app_service_plan", e.target.value)}
                          placeholder="your-linux-app-service-plan"
                          className="w-full bg-background-secondary border border-border rounded-xl px-4 py-2.5 text-foreground focus:border-primary focus:outline-none font-mono"
                        />
                      </label>
                      <label className="space-y-1.5 md:col-span-2">
                        <span className="font-bold text-foreground-muted">Application name prefix</span>
                        <input
                          type="text"
                          value={azureForm.namespace_prefix}
                          onChange={(e) => handleAzureFieldChange("namespace_prefix", e.target.value)}
                          placeholder="team-or-customer-slug"
                          className="w-full bg-background-secondary border border-border rounded-xl px-4 py-2.5 text-foreground placeholder:text-foreground-muted focus:border-primary focus:outline-none font-mono"
                        />
                      </label>
                    </div>

                    <div className="p-3.5 rounded-xl bg-primary/5 border border-primary/20 text-[11px] text-foreground-muted leading-relaxed">
                      ZeroOps builds each release in Azure, then assigns a secure public address only after Azure reports the new version ready and it responds to a reachability check. The connected identity needs permission to build images, publish applications, and assign image-pull access in this resource group.
                    </div>

                    <div className="flex justify-end">
                      <button
                        type="submit"
                        disabled={savingAzure}
                        className="px-5 py-2.5 bg-primary hover:bg-primary-hover text-white font-bold rounded-xl transition cursor-pointer shadow-md shadow-primary/10 disabled:opacity-50 flex items-center gap-1.5"
                      >
                        {savingAzure ? (
                          <>
                            <Loader2 size={12} className="animate-spin" /> Saving...
                          </>
                        ) : (
                          "Save hosting connection"
                        )}
                      </button>
                    </div>
                  </form>
                )}
              </div>

            </motion.div>
          )}

          {/* DOMAINS TAB */}
          {activeTab === "domains" && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
              <div className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
                <h3 className="font-extrabold text-sm text-foreground">Connected Domains</h3>
                
                {loadingDomains ? (
                  <div className="flex items-center gap-2 text-foreground-muted font-medium py-4 text-xs">
                    <Loader2 size={14} className="animate-spin text-primary" /> Loading domains config...
                  </div>
                ) : domains.length > 0 ? (
                  <div className="space-y-3">
                    {domains.map((dom) => (
                      <div key={dom.name} className="flex flex-col sm:flex-row sm:items-center justify-between p-3.5 rounded-xl bg-background-secondary/30 border border-border/40 text-xs gap-3">
                        <div className="space-y-0.5">
                          <p className="font-mono font-bold text-foreground flex items-center gap-1.5">
                            <Globe2 size={12} className="text-foreground-muted" />
                            {dom.name}
                          </p>
                          <p className="text-[10px] text-foreground-muted font-medium">
                            {dom.default ? "Primary system mapping" : `Added on Let's Encrypt SSL`}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 self-end sm:self-auto">
                          {/* DNS verified */}
                          {dom.dns_verified ? (
                            <span className="flex items-center gap-0.5 text-[9px] bg-success/10 border border-success/20 text-success px-2 py-0.5 rounded-full font-bold uppercase">
                              <ShieldCheck size={10} /> DNS Verified
                            </span>
                          ) : (
                            <button
                              onClick={() => handleVerifyDomain(dom.name)}
                              disabled={verifyingDomainName === dom.name}
                              className="flex items-center gap-1 text-[9px] bg-warning/15 hover:bg-warning/25 border border-warning/30 text-warning px-2.5 py-1 rounded-full font-bold uppercase cursor-pointer transition disabled:opacity-50"
                            >
                              {verifyingDomainName === dom.name ? (
                                <>
                                  <Loader2 size={8} className="animate-spin" /> Verifying
                                </>
                              ) : (
                                "Verify DNS"
                              )}
                            </button>
                          )}

                          {/* SSL active */}
                          {dom.ssl ? (
                            <button
                              onClick={() => handleRenewSSL(dom.name)}
                              disabled={renewingDomainName === dom.name}
                              className="flex items-center gap-0.5 text-[9px] bg-success/10 hover:bg-success/20 border border-success/20 text-success px-2 py-0.5 rounded-full font-bold uppercase cursor-pointer disabled:opacity-50"
                            >
                              {renewingDomainName === dom.name ? (
                                <Loader2 size={8} className="animate-spin mr-0.5" />
                              ) : (
                                <CheckCircle size={10} />
                              )}
                              SSL Active
                            </button>
                          ) : (
                            <span className="flex items-center gap-0.5 text-[9px] bg-card-hover border border-border text-foreground-muted px-2 py-0.5 rounded-full font-bold uppercase">
                              SSL Inactive
                            </span>
                          )}

                          {/* Remove custom domain */}
                          {!dom.default && (
                            <button
                              onClick={() => handleRemoveDomain(dom.name)}
                              className="p-1 hover:bg-warning/10 text-foreground-muted hover:text-warning rounded transition cursor-pointer border border-transparent hover:border-warning/20 ml-2"
                              title="Disconnect domain"
                            >
                              <Trash2 size={12} />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-foreground-muted py-4 font-medium">
                    No custom domains connected to this project yet.
                  </div>
                )}

                {/* Add domain form */}
                {selectedProjectId && (
                  <form onSubmit={handleAddDomain} className="flex gap-2 text-xs pt-2">
                    <input
                      type="text"
                      required
                      value={newDomain}
                      onChange={(e) => setNewDomain(e.target.value)}
                      placeholder="app.mycompany.com"
                      className="flex-1 bg-background-secondary border border-border rounded-xl px-4 py-2.5 text-foreground focus:border-primary focus:outline-none font-medium"
                    />
                    <button type="submit" className="px-4 py-2.5 bg-primary hover:bg-primary-hover text-white font-bold rounded-xl transition flex items-center gap-1 shadow-md shadow-primary/10 cursor-pointer">
                      <Plus size={14} /> Connect Domain
                    </button>
                  </form>
                )}
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
                      {apiKeyVisible ? apiKey || (apiKeyConfigured ? "Stored securely — regenerate to reveal a new key" : "No key available") : "••••••••••••••••••••••••••••••••••••"}
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
                    disabled={!apiKey}
                    className="px-4 bg-primary hover:bg-primary-hover text-white font-bold rounded-xl transition cursor-pointer shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {copied ? "Copied" : "Copy"}
                  </button>
                </div>
                <button
                  onClick={regenerateApiKey}
                  className="w-full py-2.5 bg-background-secondary border border-border hover:bg-card-hover text-foreground text-xs font-bold rounded-xl transition flex items-center justify-center gap-1.5 cursor-pointer shadow-sm"
                >
                  <RefreshCw size={12} className="text-foreground-muted" /> Regenerate Access Key
                </button>
              </div>

              {/* Secrets Vault */}
              <div className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
                <h3 className="font-extrabold text-sm text-foreground flex items-center gap-1.5">
                  <Shield size={16} className="text-success" /> Environment Variables (Vault Secrets)
                </h3>
                <p className="text-xs text-foreground-muted leading-normal">
                  Secret values are served by the backend secret store and injected at application runtime. Secret variables are encrypted in the secure platform vault.
                </p>
                
                {loadingSecrets ? (
                  <div className="flex items-center gap-2 text-foreground-muted font-medium py-4 text-xs">
                    <Loader2 size={14} className="animate-spin text-primary" /> Loading encrypted vault secrets...
                  </div>
                ) : secrets.length > 0 ? (
                  <div className="space-y-2 text-xs">
                    {secrets.map((sec) => (
                      <div key={sec.id} className="flex items-center justify-between p-3 rounded-xl bg-background-secondary/30 border border-border/40">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-foreground">{sec.key}</span>
                          {sec.is_secret && (
                            <span className="text-[8px] bg-success/15 border border-success/25 text-success font-semibold px-1 rounded uppercase">Secret</span>
                          )}
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="font-mono text-[10px] text-foreground-muted truncate max-w-[200px]">{sec.value}</span>
                          <button
                            onClick={() => handleDeleteSecret(sec.id, sec.key)}
                            className="p-1 hover:bg-warning/10 text-foreground-muted hover:text-warning rounded transition cursor-pointer border border-transparent hover:border-warning/20"
                            title="Delete secret"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-foreground-muted py-4 font-medium">
                    No variables defined for this project&apos;s production environment.
                  </div>
                )}

                {/* Add secret form */}
                {selectedProjectId && (
                  <form onSubmit={handleAddSecret} className="border-t border-border/40 pt-4 space-y-3 text-xs">
                    <h4 className="font-bold text-foreground">Add New Variable</h4>
                    <div className="flex flex-col sm:flex-row gap-2">
                      <input
                        type="text"
                        required
                        placeholder="KEY_NAME"
                        value={newSecretKey}
                        onChange={(e) => setNewSecretKey(e.target.value)}
                        className="flex-1 bg-background-secondary border border-border rounded-xl px-4 py-2 text-foreground focus:outline-none font-mono font-bold"
                      />
                      <input
                        type="text"
                        required
                        placeholder="value_string"
                        value={newSecretValue}
                        onChange={(e) => setNewSecretValue(e.target.value)}
                        className="flex-[2] bg-background-secondary border border-border rounded-xl px-4 py-2 text-foreground focus:outline-none font-mono"
                      />
                      <div className="flex items-center gap-2 px-1">
                        <input
                          type="checkbox"
                          id="isSecret"
                          checked={newSecretIsSecret}
                          onChange={(e) => setNewSecretIsSecret(e.target.checked)}
                          className="w-4 h-4 rounded border-border text-primary focus:ring-primary cursor-pointer"
                        />
                        <label htmlFor="isSecret" className="font-bold text-foreground-muted cursor-pointer select-none">Encrypt Secret</label>
                      </div>
                      <button
                        type="submit"
                        disabled={savingSecret}
                        className="px-4 py-2 bg-primary hover:bg-primary-hover text-white font-bold rounded-xl transition cursor-pointer shadow-md disabled:opacity-50"
                      >
                        {savingSecret ? "Saving..." : "Save"}
                      </button>
                    </div>
                  </form>
                )}
              </div>
            </motion.div>
          )}

          {/* TEAM ACCESS TAB */}
          {activeTab === "team" && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
              <div className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
                <h3 className="font-extrabold text-sm text-foreground flex items-center gap-1.5">
                  <Users size={16} className="text-primary" /> Project Access & Team Control
                </h3>
                
                {loadingMembers ? (
                  <div className="flex items-center gap-2 text-foreground-muted font-medium py-4 text-xs">
                    <Loader2 size={14} className="animate-spin text-primary" /> Loading workspace members...
                  </div>
                ) : (
                  <div className="space-y-3">
                    {members.map((mem) => (
                      <div key={mem.email} className="flex items-center justify-between p-3.5 rounded-xl bg-background-secondary/30 border border-border/40 text-xs">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center font-extrabold border border-primary/20">
                            {mem.name.charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <p className="font-bold text-foreground">{mem.name}</p>
                            <p className="text-[10px] text-foreground-muted">{mem.email}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className={`text-[9px] border px-2 py-0.5 rounded-full font-bold uppercase ${
                            mem.role === "Owner"
                              ? "bg-primary/10 border-primary/20 text-primary"
                              : mem.role === "Admin"
                              ? "bg-success/10 border-success/20 text-success"
                              : mem.role === "Developer"
                              ? "bg-accent/10 border-accent/20 text-accent"
                              : "bg-card-hover border-border text-foreground-muted"
                          }`}>
                            {mem.role}
                          </span>
                          
                          {mem.role !== "Owner" && (
                            <button
                              onClick={() => handleRemoveMember(mem.email)}
                              className="p-1 hover:bg-warning/10 text-foreground-muted hover:text-warning rounded transition cursor-pointer border border-transparent hover:border-warning/20 ml-2"
                              title="Revoke access"
                            >
                              <Trash2 size={12} />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Invite form */}
                {selectedProjectId && (
                  <form onSubmit={handleAddMember} className="border-t border-border/40 pt-4 space-y-2 text-xs">
                    <h4 className="font-bold text-foreground-muted">Invite Workspace Member</h4>
                    <div className="flex flex-col sm:flex-row gap-2">
                      <input
                        type="email"
                        required
                        placeholder="developer@mycompany.com"
                        value={newMemberEmail}
                        onChange={(e) => setNewMemberEmail(e.target.value)}
                        className="flex-1 bg-background-secondary border border-border rounded-xl px-4 py-2.5 text-foreground focus:border-primary focus:outline-none font-medium"
                      />
                      <select
                        value={newMemberRole}
                        onChange={(e) => setNewMemberRole(e.target.value)}
                        className="bg-background-secondary border border-border rounded-xl px-3 py-2.5 text-foreground focus:outline-none font-semibold cursor-pointer"
                      >
                        <option value="Admin">Admin</option>
                        <option value="Developer">Developer</option>
                        <option value="Viewer">Viewer</option>
                      </select>
                      <button
                        type="submit"
                        disabled={addingMember}
                        className="px-4 py-2.5 bg-primary hover:bg-primary-hover text-white font-bold rounded-xl transition cursor-pointer shadow-md shadow-primary/10 disabled:opacity-50"
                      >
                        {addingMember ? "Adding..." : "Add Member"}
                      </button>
                    </div>
                  </form>
                )}
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
                      <p className="text-[10px] text-foreground-muted mt-0.5">Receive immediate incident reports for OOM and container crashes</p>
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
                      <p className="text-[10px] text-foreground-muted mt-0.5">Coming soon — contact support for early access</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={false}
                      disabled
                      readOnly
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
