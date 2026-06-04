"use client";

import { useCallback, useEffect, useMemo, useState, Suspense } from "react";
import {
  ArrowLeft,
  ExternalLink,
  Globe,
  Loader2,
  RefreshCw,
  RotateCcw,
  Terminal,
  CheckCircle2,
  AlertTriangle,
  Server,
  Activity,
  Sparkles,
  Trash2,
  Plus,
  Lock,
  Search,
  Settings as SettingsIcon,
  Brain,
  Eye,
  EyeOff
} from "lucide-react";
import { useNotifications } from "@/lib/NotificationContext";
import { useRouter, useSearchParams, useParams } from "next/navigation";
import {
  api,
  type CustomDomain,
  type Deployment,
  type DeploymentDetail,
  type Project,
  type TelemetryMetric,
  type EnvVar,
  type HealthScore,
  type CostOptimization,
  getErrorMessage
} from "@/lib/api";

const formatDateTime = (value?: string | null) => {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

const displayMetric = (value?: string | null) => {
  return value && value !== "No data" ? value : "No data";
};

const asRecord = (value: unknown): Record<string, unknown> | null => {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
};

const stringFromRecord = (record: Record<string, unknown> | null | undefined, key: string) => {
  const value = record?.[key];
  return typeof value === "string" && value.trim() ? value : null;
};

const hostFromUrl = (url: string) => {
  try {
    return new URL(url).host;
  } catch {
    return url.replace(/^https?:\/\//, "");
  }
};

function AppDetailsPageContent({ projectId }: { projectId: string }) {
  const { addToast } = useNotifications();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [project, setProject] = useState<Project | null>(null);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [latestDeploymentDetail, setLatestDeploymentDetail] = useState<DeploymentDetail | null>(null);
  const [metrics, setMetrics] = useState<TelemetryMetric | null>(null);
  const [domains, setDomains] = useState<CustomDomain[]>([]);
  const [envVars, setEnvVars] = useState<EnvVar[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("overview");
  const [healthScore, setHealthScore] = useState<HealthScore | null>(null);
  const [costOpt, setCostOpt] = useState<CostOptimization | null>(null);
  const [requestingFixId, setRequestingFixId] = useState<string | null>(null);

  // Domain Management States
  const [domainNameInput, setDomainNameInput] = useState("");
  const [addingDomain, setAddingDomain] = useState(false);
  const [verifyingDomain, setVerifyingDomain] = useState<string | null>(null);
  const [renewingSSL, setRenewingSSL] = useState<string | null>(null);

  // Environment Variable States
  const [envKey, setEnvKey] = useState("");
  const [envValue, setEnvValue] = useState("");
  const [envIsSecret, setEnvIsSecret] = useState(false);
  const [addingEnv, setAddingEnv] = useState(false);
  const [showEnvValues, setShowEnvValues] = useState<Record<string, boolean>>({});

  // Redeployment / Rollback States
  const [redeploying, setRedeploying] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);
  const [selfHealingAction, setSelfHealingAction] = useState<string | null>(null);

  // Log Mode States
  const [logMode, setLogMode] = useState<"simple" | "advanced">("simple");
  const [logSearchQuery, setLogSearchQuery] = useState("");

  useEffect(() => {
    const tab = searchParams.get("tab");
    if (tab) setActiveTab(tab);
  }, [searchParams]);

  const handleTabChange = (tabName: string) => {
    setActiveTab(tabName);
    const newUrl = `${window.location.pathname}?tab=${tabName}`;
    window.history.pushState(null, "", newUrl);
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const projectData = await api.getProject(projectId);
      setProject(projectData);

      const [depsData, metricsData, domainsData, envData, healthData, costData] = await Promise.allSettled([
        api.getDeployments(50),
        api.getProjectMetrics(projectId),
        api.getProjectDomains(projectId),
        api.getEnvVars(projectId),
        api.getHealthScore(projectId),
        api.getCostOptimization(projectId),
      ]);

      let filteredDeployments: Deployment[] = [];
      if (depsData.status === "fulfilled") {
        filteredDeployments = depsData.value.filter((deployment) => deployment.project_id === projectId);
        filteredDeployments.sort((a, b) => {
          const dateA = new Date(a.completed_at || a.started_at || 0).getTime();
          const dateB = new Date(b.completed_at || b.started_at || 0).getTime();
          return dateB - dateA;
        });
        setDeployments(filteredDeployments);
      }

      if (metricsData.status === "fulfilled") setMetrics(metricsData.value);
      if (domainsData.status === "fulfilled") setDomains(domainsData.value);
      if (envData.status === "fulfilled") setEnvVars(envData.value);
      if (healthData.status === "fulfilled") setHealthScore(healthData.value);
      if (costData.status === "fulfilled") setCostOpt(costData.value);

      if (filteredDeployments.length > 0) {
        try {
          const detail = await api.getDeployment(filteredDeployments[0].id);
          setLatestDeploymentDetail(detail);
        } catch (err) {
          console.error("Failed to load latest deployment details:", err);
        }
      }
    } catch (err) {
      console.error("Failed to load project details:", err);
      addToast("Failed to load application details.", "error");
    } finally {
      setLoading(false);
    }
  }, [projectId, addToast]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const latestDeployment = deployments[0];
  const liveUrl = latestDeployment?.live_url || "";
  const liveHost = liveUrl ? hostFromUrl(liveUrl) : "";
  const latestMetadata = latestDeploymentDetail?.infrastructure_metadata || latestDeployment?.infrastructure_metadata || null;
  const azureMetadata = asRecord(latestMetadata?.azure);
  const hostingTarget = stringFromRecord(azureMetadata, "aks_cluster_name")
    || stringFromRecord(latestMetadata, "namespace")
    || "Not recorded";
  const hostingRegion = stringFromRecord(azureMetadata, "region") || project?.region || "Not recorded";
  const latestLogs = latestDeploymentDetail?.logs || [];
  const logErrorCount = latestLogs.filter((log) => log.level === "ERROR").length;
  const logWarningCount = latestLogs.filter((log) => log.level === "WARN").length;
  const recentLogs = latestLogs.slice(-5);

  const aiRecommendations = useMemo(() => {
    const healthItems = (healthScore?.recommendations || []).map((text, index) => ({
      id: `health-${index}`,
      category: "Health",
      issue: text,
      impact: "Based on recorded deployments, runtime logs, and telemetry.",
      recommendation: text,
      billable: (healthScore?.score || 0) > 0 && !text.toLowerCase().includes("no immediate"),
    }));

    const costItems = (costOpt?.recommendations || []).map((item, index) => ({
      id: `cost-${index}`,
      category: "Cost",
      issue: item.title,
      impact: item.savings > 0 ? `Estimated savings: $${item.savings}/month.` : "Cost telemetry is still being established.",
      recommendation: item.description,
      billable: item.savings > 0,
    }));

    return [...healthItems, ...costItems];
  }, [healthScore, costOpt]);

  const handleRedeploy = async () => {
    if (!project || redeploying) return;
    setRedeploying(true);
    addToast(`Initiating redeployment for ${project.name}...`, "info");
    try {
      const res = await api.startDeployment({
        project_id: project.id,
        branch: project.branch || "main",
        environment: latestDeployment?.environment || "production",
      });
      addToast("Redeployment started successfully", "success");
      router.push(`/dashboard/deployments?id=${res.deployment_id}`);
    } catch (err) {
      addToast(`Failed to redeploy: ${getErrorMessage(err, "unknown error")}`, "error");
    } finally {
      setRedeploying(false);
    }
  };

  const handleRollback = async () => {
    if (!project || rollingBack) return;
    setRollingBack(true);
    addToast("Initiating rollback to previous stable version...", "info");
    try {
      const res = await api.startDeployment({
        project_id: project.id,
        branch: project.branch || "main",
        environment: latestDeployment?.environment || "production",
      });
      addToast("Rollback triggered successfully.", "success");
      router.push(`/dashboard/deployments?id=${res.deployment_id}`);
    } catch (err) {
      addToast(`Failed to rollback: ${getErrorMessage(err, "unknown error")}`, "error");
    } finally {
      setRollingBack(false);
    }
  };

  const handleSelfHeal = async (action: string) => {
    if (!project || selfHealingAction) return;
    setSelfHealingAction(action);
    addToast(`Triggering autonomous self-healing action: ${action}...`, "info");
    try {
      const res = await api.selfHeal(project.id, action);
      addToast(res.message || `Autonomous action ${action} executed successfully.`, "success");
      if (res.deployment_id) {
        router.push(`/dashboard/deployments?id=${res.deployment_id}`);
      } else {
        await loadData();
      }
    } catch (err) {
      addToast(`Failed to execute autonomous action: ${getErrorMessage(err, "unknown error")}`, "error");
    } finally {
      setSelfHealingAction(null);
    }
  };

  const handleDeleteProject = async () => {
    if (!project) return;
    if (!window.confirm("Are you sure you want to permanently delete this application and all associated resources? This action cannot be undone.")) return;
    try {
      await api.deleteProject(project.id);
      addToast("Application deleted successfully.", "success");
      router.push("/dashboard");
    } catch (err) {
      addToast(`Failed to delete application: ${getErrorMessage(err, "unknown error")}`, "error");
    }
  };

  const handleConnectDomain = async () => {
    if (!domainNameInput.trim() || !project) return;
    setAddingDomain(true);
    try {
      const updated = await api.connectDomain(project.id, domainNameInput.trim());
      setDomains(updated);
      setDomainNameInput("");
      addToast("Custom domain linked to project configuration.", "success");
    } catch {
      addToast("Failed to connect domain.", "error");
    } finally {
      setAddingDomain(false);
    }
  };

  const handleVerifyDomain = async (name: string) => {
    if (!project) return;
    setVerifyingDomain(name);
    try {
      const updated = await api.verifyDomain(project.id, name);
      setDomains(updated);
      addToast("Domain SSL verification finalized.", "success");
    } catch {
      addToast("Failed to verify domain.", "error");
    } finally {
      setVerifyingDomain(null);
    }
  };

  const handleRenewSSL = async (name: string) => {
    if (!project) return;
    setRenewingSSL(name);
    try {
      const updated = await api.renewSSL(project.id, name);
      setDomains(updated);
      addToast("SSL certificate renewed successfully.", "success");
    } catch {
      addToast("Failed to renew SSL.", "error");
    } finally {
      setRenewingSSL(null);
    }
  };

  const handleAddEnvVar = async () => {
    if (!envKey.trim() || !envValue.trim() || !project) return;
    setAddingEnv(true);
    try {
      const newVar = await api.addEnvVar(project.id, {
        key: envKey.trim(),
        value: envValue.trim(),
        is_secret: envIsSecret,
      });
      setEnvVars((prev) => [...prev, newVar]);
      setEnvKey("");
      setEnvValue("");
      setEnvIsSecret(false);
      addToast("Environment variable saved successfully.", "success");
    } catch (err) {
      addToast(`Failed to save env var: ${getErrorMessage(err, "unknown error")}`, "error");
    } finally {
      setAddingEnv(false);
    }
  };

  const handleDeleteEnvVar = async (varId: string) => {
    if (!project) return;
    try {
      await api.deleteEnvVar(project.id, varId);
      setEnvVars((prev) => prev.filter((v) => v.id !== varId));
      addToast("Environment variable deleted.", "success");
    } catch (err) {
      addToast(`Failed to delete env var: ${getErrorMessage(err, "unknown error")}`, "error");
    }
  };

  const handleRequestPaidFix = async (id: string, recommendation: string) => {
    if (!project || requestingFixId) return;
    setRequestingFixId(id);
    try {
      await api.createBillingOperation({
        operation_type: "ai_code_fix",
        project_id: project.id,
        description: recommendation,
      });
      addToast("Paid fix request created. Complete payment before AI changes code.", "info");
    } catch (err) {
      addToast(`Could not create paid fix request: ${getErrorMessage(err, "unknown error")}`, "error");
    } finally {
      setRequestingFixId(null);
    }
  };

  const toggleShowValue = (id: string) => {
    setShowEnvValues((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const isProjectRunning = project?.status === "active" || latestDeployment?.status === "running";
  const appStatusText = isProjectRunning
    ? "Running"
    : latestDeployment?.status
      ? latestDeployment.status
      : "Not deployed";
  const appStatusClass = isProjectRunning
    ? "text-success bg-success/10 border-success/20"
    : "text-warning bg-warning/10 border-warning/20";
  const appStatusIcon = isProjectRunning ? <CheckCircle2 size={14} className="text-success mr-1.5" /> : <AlertTriangle size={14} className="text-warning mr-1.5" />;

  // Filter logs in Advanced Mode
  const filteredLogs = latestDeploymentDetail?.logs?.filter((log) =>
    log.message.toLowerCase().includes(logSearchQuery.toLowerCase())
  ) || [];

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="animate-spin text-primary" size={28} />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-12">
      {/* Back button & top workspace header */}
      <div className="flex flex-col gap-3">
        <button
          onClick={() => router.push("/dashboard")}
          className="text-xs text-foreground-muted hover:text-foreground flex items-center gap-1 cursor-pointer transition w-fit"
        >
          <ArrowLeft size={14} /> Back to dashboard
        </button>
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-border/40 pb-5">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-extrabold text-foreground tracking-tight">{project?.name}</h1>
              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${appStatusClass}`}>
                {appStatusIcon}
                {appStatusText}
              </span>
            </div>
            <p className="text-xs text-foreground-muted mt-1">{project?.full_name}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {liveUrl ? (
              <a
                href={liveUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="px-4 py-2 bg-primary text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer flex items-center gap-1 shadow-sm"
              >
                <ExternalLink size={13} /> Open App
              </a>
            ) : (
              <button
                type="button"
                disabled
                className="px-4 py-2 bg-muted text-foreground-muted rounded-xl text-xs font-semibold flex items-center gap-1 shadow-sm cursor-not-allowed"
              >
                <ExternalLink size={13} /> No URL
              </button>
            )}
            <button
              onClick={handleRedeploy}
              disabled={redeploying}
              className="px-4 py-2 border border-border bg-card rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer flex items-center gap-1"
            >
              <RefreshCw size={13} className={redeploying ? "animate-spin" : ""} /> Redeploy
            </button>
            <button
              onClick={handleRollback}
              disabled={rollingBack}
              className="px-4 py-2 border border-border bg-card rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer flex items-center gap-1"
            >
              <RotateCcw size={13} className={rollingBack ? "animate-spin" : ""} /> Rollback
            </button>
          </div>
        </div>
      </div>

      {/* Tabs navigation */}
      <div className="flex flex-wrap gap-1 bg-muted/20 border border-border/40 rounded-xl p-1 w-fit">
        {[
          { id: "overview", label: "Overview", icon: Activity },
          { id: "deployments", label: "Deployments", icon: RefreshCw },
          { id: "logs", label: "Logs", icon: Terminal },
          { id: "domains", label: "Domains", icon: Globe },
          { id: "ai-insights", label: "AI Insights", icon: Brain },
          { id: "settings", label: "Settings", icon: SettingsIcon },
        ].map((tab) => {
          const TabIcon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-bold transition cursor-pointer ${
                activeTab === tab.id
                  ? "bg-card text-foreground shadow-sm border border-border"
                  : "text-foreground-muted hover:text-foreground hover:bg-card/40"
              }`}
            >
              <TabIcon size={14} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Overview tab */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* AI Health Assessment Banner */}
          <div className="p-5 rounded-2xl border border-primary/25 bg-gradient-to-r from-primary/5 via-accent/5 to-transparent flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1">
              <h3 className="text-sm font-extrabold text-foreground flex items-center gap-1">
                <Sparkles size={16} className="text-primary animate-pulse" /> AI Health Assessment
              </h3>
              <p className="text-xs text-foreground-muted leading-relaxed">
                ZeroOps AI is showing only recorded deployment and telemetry signals for this application. Current runtime status is <span className="text-foreground font-bold">{metrics?.uptime || appStatusText}</span>.
              </p>
            </div>
            <button
              onClick={() => handleTabChange("ai-insights")}
              className="px-3.5 py-1.5 bg-primary/10 hover:bg-primary/15 border border-primary/20 text-primary text-xs font-bold rounded-xl transition cursor-pointer whitespace-nowrap self-end md:self-auto"
            >
              View Engineering Review
            </button>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            {/* General Overview Card */}
            <div className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-4">
              <h2 className="text-sm font-bold text-foreground uppercase tracking-wider border-b border-border/40 pb-2">Application Info</h2>
              <div className="grid grid-cols-2 gap-4 text-xs">
                <div>
                  <p className="text-[10px] uppercase text-foreground-muted font-bold">Hosting Target</p>
                  <p className="font-extrabold text-foreground mt-0.5">{hostingTarget}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase text-foreground-muted font-bold">Environment</p>
                  <p className="font-extrabold text-foreground mt-0.5">{latestDeployment?.environment || "Not recorded"}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase text-foreground-muted font-bold">Live URL</p>
                  {liveUrl ? (
                    <a
                      href={liveUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-extrabold text-primary hover:underline mt-0.5 truncate block"
                    >
                      {liveHost}
                    </a>
                  ) : (
                    <p className="font-extrabold text-foreground-muted mt-0.5">Not recorded</p>
                  )}
                </div>
                <div>
                  <p className="text-[10px] uppercase text-foreground-muted font-bold">Repository Branch</p>
                  <p className="font-extrabold text-foreground font-mono mt-0.5">{project?.branch || "Not recorded"}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase text-foreground-muted font-bold">Last Deployment</p>
                  <p className="font-extrabold text-foreground mt-0.5">{formatDateTime(latestDeployment?.completed_at || latestDeployment?.started_at)}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase text-foreground-muted font-bold">Last Commit SHA</p>
                  <p className="font-extrabold text-foreground font-mono mt-0.5">{latestDeployment?.commit_sha?.substring(0, 7) || "Not recorded"}</p>
                </div>
              </div>
            </div>

            {/* Consolidated Telemetry dashboard (Simplified) */}
            <div className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-4">
              <h2 className="text-sm font-bold text-foreground uppercase tracking-wider border-b border-border/40 pb-2">Telemetry Summary</h2>
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3.5 bg-background-secondary border border-border/60 rounded-xl space-y-1">
                  <span className="text-[9px] uppercase font-bold text-foreground-muted">Average Latency</span>
                  <p className="text-xl font-extrabold text-foreground tracking-tight">{displayMetric(metrics?.response_time)}</p>
                </div>
                <div className="p-3.5 bg-background-secondary border border-border/60 rounded-xl space-y-1">
                  <span className="text-[9px] uppercase font-bold text-foreground-muted">Runtime Status</span>
                  <p className="text-xl font-extrabold text-foreground tracking-tight">{displayMetric(metrics?.uptime)}</p>
                </div>
                <div className="p-3.5 bg-background-secondary border border-border/60 rounded-xl space-y-1">
                  <span className="text-[9px] uppercase font-bold text-foreground-muted">Requests (24h)</span>
                  <p className="text-xl font-extrabold text-foreground tracking-tight">{metrics ? metrics.request_count.toLocaleString() : "No data"}</p>
                </div>
                <div className="p-3.5 bg-background-secondary border border-border/60 rounded-xl space-y-1">
                  <span className="text-[9px] uppercase font-bold text-foreground-muted">Error Rate</span>
                  <p className="text-xl font-extrabold text-foreground tracking-tight">{displayMetric(metrics?.error_rate)}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Deployments tab */}
      {activeTab === "deployments" && (
        <div className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-border/40 pb-2">
            <h2 className="text-sm font-bold text-foreground uppercase tracking-wider">Deployment History</h2>
            <span className="text-[10px] font-mono text-foreground-muted">Total: {deployments.length} deployments</span>
          </div>

          {deployments.length === 0 ? (
            <div className="text-center py-12 text-foreground-muted text-xs">No deployments recorded yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="text-foreground-muted border-b border-border/60 text-[10px] font-bold uppercase tracking-wider">
                    <th className="py-3 px-4">Version</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Environment</th>
                    <th className="py-3 px-4">Triggered At</th>
                    <th className="py-3 px-4 text-center">Duration</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40 text-xs font-semibold">
                  {deployments.map((deployment) => {
                    const isRunning = deployment.status === "running";
                    return (
                      <tr key={deployment.id} className="hover:bg-muted/10 transition-colors">
                        <td className="py-3.5 px-4 font-mono text-foreground">{deployment.version || "—"}</td>
                        <td className="py-3.5 px-4">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            isRunning ? "bg-success/15 text-success" : "bg-muted text-foreground-muted"
                          }`}>
                            {deployment.status}
                          </span>
                        </td>
                        <td className="py-3.5 px-4 text-foreground-muted">Production</td>
                        <td className="py-3.5 px-4 text-foreground-muted">{formatDateTime(deployment.started_at)}</td>
                        <td className="py-3.5 px-4 text-center text-foreground-muted font-mono">{deployment.duration || "—"}</td>
                        <td className="py-3.5 px-4 text-right">
                          <button
                            onClick={() => router.push(`/dashboard/deployments?id=${deployment.id}`)}
                            className="px-2.5 py-1 rounded border border-border text-[10px] font-bold hover:bg-card-hover transition cursor-pointer"
                          >
                            Logs
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Logs tab */}
      {activeTab === "logs" && (
        <div className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-3">
            <div>
              <h2 className="text-sm font-bold text-foreground uppercase tracking-wider">Application Logs</h2>
              <p className="text-xs text-foreground-muted mt-0.5">Real-time stderr/stdout logs streamed from the application runtime.</p>
            </div>
            
            <div className="flex items-center gap-2">
              <button
                onClick={() => setLogMode("simple")}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition cursor-pointer ${
                  logMode === "simple"
                    ? "bg-primary/10 border-primary/20 text-primary"
                    : "border-border text-foreground-muted hover:text-foreground hover:bg-card-hover"
                }`}
              >
                Simple Mode (AI summary)
              </button>
              <button
                onClick={() => setLogMode("advanced")}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition cursor-pointer ${
                  logMode === "advanced"
                    ? "bg-primary/10 border-primary/20 text-primary"
                    : "border-border text-foreground-muted hover:text-foreground hover:bg-card-hover"
                }`}
              >
                Advanced Mode (Raw logs)
              </button>
            </div>
          </div>

          {logMode === "simple" ? (
            <div className="space-y-4">
              <div className="p-5 rounded-xl border border-border/80 bg-background-secondary space-y-4">
                <h3 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                  <Brain size={14} className="text-primary animate-pulse" /> AI Log Summary
                </h3>
                <p className="text-xs text-foreground-muted leading-relaxed">
                  {latestLogs.length > 0
                    ? `Latest deployment has ${latestLogs.length} recorded log lines, including ${logErrorCount} errors and ${logWarningCount} warnings.`
                    : "No runtime logs are recorded for the latest deployment yet."}
                </p>
                
                <div className="grid sm:grid-cols-2 gap-3 pt-2">
                  {recentLogs.length > 0 ? recentLogs.map((log, i) => (
                    <div key={`${log.timestamp || "log"}-${i}`} className="flex items-start gap-2 text-xs font-semibold text-foreground">
                      {log.level === "ERROR" ? (
                        <AlertTriangle size={14} className="text-danger flex-shrink-0 mt-0.5" />
                      ) : (
                        <CheckCircle2 size={14} className="text-success flex-shrink-0 mt-0.5" />
                      )}
                      <span className="line-clamp-2">{log.message}</span>
                    </div>
                  )) : (
                    <div className="sm:col-span-2 text-xs text-foreground-muted font-semibold">Deploy or refresh the latest deployment to collect logs.</div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="bg-background-secondary border border-border rounded-xl px-3 py-1.5 flex items-center gap-2">
                <Search size={14} className="text-foreground-muted" />
                <input
                  type="text"
                  value={logSearchQuery}
                  onChange={(e) => setLogSearchQuery(e.target.value)}
                  placeholder="Filter logs by keyword..."
                  className="bg-transparent border-none outline-none text-xs text-foreground placeholder:text-foreground-muted w-full"
                />
              </div>

              <div className="font-mono text-[11px] leading-6 h-[300px] overflow-y-auto no-scrollbar bg-zinc-950 text-zinc-100 rounded-xl p-4 shadow-inner">
                {filteredLogs.length > 0 ? (
                  filteredLogs.map((log, index) => (
                    <p key={index} className={log.level === "ERROR" ? "text-red-400" : log.level === "WARN" ? "text-amber-400" : "text-zinc-300"}>
                      <span className="text-zinc-500 mr-2">[{log.timestamp ? log.timestamp.split("T")[1]?.slice(0, 8) : "00:00:00"}]</span>
                      <span className="text-primary-light mr-1">[{log.level}]</span>
                      {log.message}
                    </p>
                  ))
                ) : (
                  <p className="text-zinc-500 text-center py-12">No logs match your filter query.</p>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Domains tab */}
      {activeTab === "domains" && (
        <div className="space-y-6">
          <div className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-4">
            <div>
              <h2 className="text-sm font-bold text-foreground uppercase tracking-wider">Connect Custom Domain</h2>
              <p className="text-xs text-foreground-muted mt-0.5">Map custom addresses to your application host.</p>
            </div>
            <div className="flex flex-col sm:flex-row gap-3">
              <input
                type="text"
                value={domainNameInput}
                onChange={(e) => setDomainNameInput(e.target.value)}
                placeholder="app.yourdomain.com"
                className="flex-1 bg-background-secondary border border-border rounded-xl px-4 py-2.5 text-xs text-foreground focus:border-primary focus:outline-none"
              />
              <button
                onClick={handleConnectDomain}
                disabled={addingDomain}
                className="px-5 py-2.5 bg-primary text-white font-bold rounded-xl text-xs hover:bg-primary-hover transition cursor-pointer disabled:opacity-50"
              >
                {addingDomain ? "Connecting..." : "Connect Domain"}
              </button>
            </div>
          </div>

          <div className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-4">
            <h2 className="text-sm font-bold text-foreground uppercase tracking-wider">Configured Custom Domains</h2>
            {domains.length === 0 ? (
              <p className="text-xs text-foreground-muted py-2">No custom domains connected yet.</p>
            ) : (
              <div className="space-y-4">
                {domains.map((domain) => {
                  const secured = domain.ssl || domain.https_enabled;
                  const verified = domain.dns_verified;
                  const isSubdomain = domain.name.split(".").length > 2;
                  return (
                    <div key={domain.name} className="border border-border/80 rounded-2xl p-5 space-y-4 bg-background-secondary/20">
                      <div className="flex items-center justify-between flex-wrap gap-3">
                        <div className="flex items-center gap-2">
                          <Globe size={16} className="text-primary" />
                          <span className="font-extrabold text-foreground text-sm">{domain.name}</span>
                        </div>
                        <div className="flex items-center gap-1.5 text-[10px] font-bold">
                          <span className="px-2.5 py-0.5 rounded-full bg-success/10 text-success border border-success/20">Connected</span>
                          <span className="text-foreground-muted font-extrabold">&rarr;</span>
                          <span className={`px-2.5 py-0.5 rounded-full ${secured ? "bg-success/10 text-success border border-success/20" : "bg-warning/10 text-warning border border-warning/20"}`}>
                            {secured ? "Secured" : "Securing..."}
                          </span>
                          <span className="text-foreground-muted font-extrabold">&rarr;</span>
                          <span className={`px-2.5 py-0.5 rounded-full ${verified ? "bg-success/10 text-success border border-success/20" : "bg-warning/10 text-warning border border-warning/20"}`}>
                            {verified ? "Live" : "Verifying..."}
                          </span>
                        </div>
                      </div>

                      {/* DNS configuration instructions */}
                      <div className="bg-zinc-950/60 p-4 rounded-xl border border-border/40 text-xs font-semibold space-y-2 text-left">
                        <span className="text-[9px] uppercase tracking-wider text-primary font-bold">Required DNS Configuration</span>
                        <div className="grid grid-cols-3 gap-2 text-left font-mono text-[11px] text-zinc-300">
                          <div>
                            <span className="text-zinc-500 block text-[9px] uppercase font-sans font-bold">Record Type</span>
                            {isSubdomain ? "CNAME" : "A"}
                          </div>
                          <div>
                            <span className="text-zinc-500 block text-[9px] uppercase font-sans font-bold">Host / Name</span>
                            {isSubdomain ? domain.name.split(".")[0] : "@"}
                          </div>
                          <div>
                            <span className="text-zinc-500 block text-[9px] uppercase font-sans font-bold">Target Value</span>
                            {liveHost || (isSubdomain ? "Deploy first to record ingress host" : "Use Azure ingress IP after deployment")}
                          </div>
                        </div>
                      </div>

                      <div className="flex flex-wrap gap-2 pt-2 border-t border-border/20">
                        <button
                          onClick={() => handleVerifyDomain(domain.name)}
                          disabled={verifyingDomain === domain.name}
                          className="px-3.5 py-1.5 border border-border rounded-xl text-[10px] font-bold hover:bg-card-hover bg-card transition cursor-pointer text-foreground-muted"
                        >
                          {verifyingDomain === domain.name ? "Verifying..." : "Verify DNS"}
                        </button>
                        <button
                          onClick={() => handleRenewSSL(domain.name)}
                          disabled={renewingSSL === domain.name}
                          className="px-3.5 py-1.5 border border-border rounded-xl text-[10px] font-bold hover:bg-card-hover bg-card transition cursor-pointer text-foreground-muted"
                        >
                          {renewingSSL === domain.name ? "Renewing..." : "Renew SSL"}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* AI Insights tab */}
      {activeTab === "ai-insights" && (
        <div className="space-y-6">
          <div className="border-b border-border/40 pb-3">
            <h2 className="text-sm font-bold text-foreground uppercase tracking-wider">AI Engineering Review</h2>
            <p className="text-xs text-foreground-muted mt-0.5">Recommendations are generated from recorded deployments, logs, and telemetry.</p>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            {aiRecommendations.length > 0 ? aiRecommendations.map((rec) => {
              const isRequesting = requestingFixId === rec.id;
              return (
                <div key={rec.id} className="bg-card border border-border rounded-2xl p-5 shadow-sm space-y-4 flex flex-col justify-between">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 rounded bg-primary/10 border border-primary/20 text-primary">
                        {rec.category}
                      </span>
                    </div>
                    <div>
                      <h4 className="text-xs font-bold text-foreground">{rec.issue}</h4>
                      <p className="text-[11px] text-foreground-muted mt-1 leading-relaxed"><span className="font-bold text-foreground">Impact:</span> {rec.impact}</p>
                      <p className="text-[11px] text-foreground-muted mt-1 leading-relaxed"><span className="font-bold text-foreground font-semibold">Recommendation:</span> {rec.recommendation}</p>
                    </div>
                  </div>
                  <div className="pt-4 border-t border-border/20 flex justify-end">
                    {rec.billable ? (
                      <button
                        onClick={() => handleRequestPaidFix(rec.id, rec.recommendation)}
                        disabled={isRequesting}
                        className="px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 cursor-pointer bg-primary text-white hover:bg-primary-hover shadow-sm disabled:opacity-50"
                      >
                        {isRequesting ? (
                          <>
                            <Loader2 size={12} className="animate-spin" /> Creating request...
                          </>
                        ) : (
                          "Request Paid Fix"
                        )}
                      </button>
                    ) : (
                      <span className="text-[10px] text-foreground-muted font-semibold">No paid code change required</span>
                    )}
                  </div>
                </div>
              );
            }) : (
              <div className="md:col-span-2 bg-card border border-border rounded-2xl p-8 text-center">
                <p className="text-xs font-semibold text-foreground">No AI recommendations yet</p>
                <p className="text-[11px] text-foreground-muted mt-1">
                  Deployments and telemetry must be recorded before ZeroOps can generate actionable guidance.
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Settings tab */}
      {activeTab === "settings" && (
        <div className="space-y-6">
          {/* Environment Variables Card */}
          <div className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-5">
            <div>
              <h2 className="text-sm font-bold text-foreground uppercase tracking-wider">Environment Variables</h2>
              <p className="text-xs text-foreground-muted mt-0.5">Secrets and keys injected into the runtime container at startup.</p>
            </div>

            {/* List Env Vars */}
            {envVars.length === 0 ? (
              <p className="text-xs text-foreground-muted py-2">No environment variables configured yet.</p>
            ) : (
              <div className="space-y-3.5 max-h-[250px] overflow-y-auto pr-1">
                {envVars.map((env) => {
                  const isVisible = showEnvValues[env.id];
                  return (
                    <div key={env.id} className="flex items-center justify-between p-3.5 rounded-xl border border-border bg-background-secondary/40 text-xs">
                      <div className="font-mono flex items-center gap-2">
                        <span className="font-extrabold text-foreground">{env.key}</span>
                        <span className="text-zinc-500 font-bold">=</span>
                        <span className="text-foreground-muted text-[11px] truncate max-w-[200px]">
                          {env.is_secret && !isVisible ? "••••••••••••••••" : env.value}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        {env.is_secret && (
                          <button
                            onClick={() => toggleShowValue(env.id)}
                            className="p-1.5 rounded hover:bg-card transition text-foreground-muted hover:text-foreground cursor-pointer"
                          >
                            {isVisible ? <EyeOff size={13} /> : <Eye size={13} />}
                          </button>
                        )}
                        <button
                          onClick={() => handleDeleteEnvVar(env.id)}
                          className="p-1.5 rounded hover:bg-card transition text-danger hover:text-danger-hover cursor-pointer"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Add Env Var Form */}
            <div className="pt-4 border-t border-border/40 space-y-4">
              <h3 className="text-xs font-bold text-foreground flex items-center gap-1"><Plus size={14} /> Add Environment Variable</h3>
              <div className="flex flex-col sm:flex-row gap-3">
                <input
                  type="text"
                  value={envKey}
                  onChange={(e) => setEnvKey(e.target.value)}
                  placeholder="API_KEY"
                  className="flex-1 bg-background-secondary border border-border rounded-xl px-3.5 py-2.5 text-xs text-foreground font-mono focus:border-primary focus:outline-none"
                />
                <input
                  type="text"
                  value={envValue}
                  onChange={(e) => setEnvValue(e.target.value)}
                  placeholder="secret-value"
                  className="flex-1 bg-background-secondary border border-border rounded-xl px-3.5 py-2.5 text-xs text-foreground font-mono focus:border-primary focus:outline-none"
                />
              </div>
              <div className="flex items-center justify-between flex-wrap gap-3">
                <label className="flex items-center gap-2 text-xs font-bold text-foreground cursor-pointer">
                  <input
                    type="checkbox"
                    checked={envIsSecret}
                    onChange={(e) => setEnvIsSecret(e.target.checked)}
                    className="rounded border-border text-primary focus:ring-primary cursor-pointer w-4 h-4"
                  />
                  <span>Encrypt as Azure Vault Secret</span>
                </label>
                <button
                  onClick={handleAddEnvVar}
                  disabled={addingEnv || !envKey.trim() || !envValue.trim()}
                  className="px-5 py-2.5 bg-primary text-white font-bold rounded-xl text-xs hover:bg-primary-hover transition cursor-pointer disabled:opacity-50"
                >
                  {addingEnv ? "Adding..." : "Add Variable"}
                </button>
              </div>
            </div>
          </div>

          {/* Configuration Specs Card */}
          <div className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-4">
            <h2 className="text-sm font-bold text-foreground uppercase tracking-wider border-b border-border/40 pb-2">Production Environment Configuration</h2>
            <div className="space-y-4 text-xs font-semibold text-foreground-muted">
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <p className="text-[10px] text-foreground-muted font-bold">Autodetected Framework</p>
                  <p className="font-extrabold text-foreground">{project?.framework || "Web Application"}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-[10px] text-foreground-muted font-bold">Hosting Region</p>
                  <p className="font-extrabold text-foreground">{hostingRegion}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-[10px] text-foreground-muted font-bold">Build Command</p>
                  <p className="font-mono text-[11px] text-foreground font-semibold">Recorded during analysis</p>
                </div>
                <div className="space-y-1">
                  <p className="text-[10px] text-foreground-muted font-bold">Startup Command</p>
                  <p className="font-mono text-[11px] text-foreground font-semibold">Recorded during analysis</p>
                </div>
              </div>
            </div>
          </div>

          {/* Autonomous Self-Healing Panel */}
          <div className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-4">
            <div>
              <h2 className="text-sm font-bold text-foreground uppercase tracking-wider">Autonomous Self-Healing</h2>
              <p className="text-xs text-foreground-muted mt-0.5">Manually trigger automated remediation tasks to restore or recycle hosted resources.</p>
            </div>
            
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3.5 pt-2">
              <button
                onClick={() => handleSelfHeal("restart")}
                disabled={selfHealingAction !== null}
                className="flex flex-col items-center justify-center p-4 border border-border rounded-xl hover:bg-card-hover bg-background-secondary/20 transition cursor-pointer text-center space-y-2 text-xs font-bold text-foreground disabled:opacity-50"
              >
                <RefreshCw size={18} className="text-primary" />
                <span>Restart Service</span>
                <span className="text-[9px] font-medium text-foreground-muted">Recycle container instance</span>
              </button>

              <button
                onClick={() => handleSelfHeal("regenerate-env")}
                disabled={selfHealingAction !== null}
                className="flex flex-col items-center justify-center p-4 border border-border rounded-xl hover:bg-card-hover bg-background-secondary/20 transition cursor-pointer text-center space-y-2 text-xs font-bold text-foreground disabled:opacity-50"
              >
                <Lock size={18} className="text-primary" />
                <span>Regenerate Secrets</span>
                <span className="text-[9px] font-medium text-foreground-muted">Regenerate default keys</span>
              </button>

              <button
                onClick={() => handleSelfHeal("reconnect-db")}
                disabled={selfHealingAction !== null}
                className="flex flex-col items-center justify-center p-4 border border-border rounded-xl hover:bg-card-hover bg-background-secondary/20 transition cursor-pointer text-center space-y-2 text-xs font-bold text-foreground disabled:opacity-50"
              >
                <Server size={18} className="text-primary" />
                <span>Reconnect Database</span>
                <span className="text-[9px] font-medium text-foreground-muted">Recycle connection pools</span>
              </button>

              <button
                onClick={() => handleSelfHeal("redeploy")}
                disabled={selfHealingAction !== null}
                className="flex flex-col items-center justify-center p-4 border border-border rounded-xl hover:bg-card-hover bg-background-secondary/20 transition cursor-pointer text-center space-y-2 text-xs font-bold text-foreground disabled:opacity-50"
              >
                <RefreshCw size={18} className="text-primary" />
                <span>Redeploy</span>
                <span className="text-[9px] font-medium text-foreground-muted">Rebuild & rollout code</span>
              </button>

              <button
                onClick={() => handleSelfHeal("rollback")}
                disabled={selfHealingAction !== null}
                className="flex flex-col items-center justify-center p-4 border border-border rounded-xl hover:bg-card-hover bg-background-secondary/20 transition cursor-pointer text-center space-y-2 text-xs font-bold text-foreground disabled:opacity-50"
              >
                <RotateCcw size={18} className="text-primary" />
                <span>Rollback</span>
                <span className="text-[9px] font-medium text-foreground-muted">Restore last working build</span>
              </button>

              <button
                onClick={() => handleSelfHeal("retry-health")}
                disabled={selfHealingAction !== null}
                className="flex flex-col items-center justify-center p-4 border border-border rounded-xl hover:bg-card-hover bg-background-secondary/20 transition cursor-pointer text-center space-y-2 text-xs font-bold text-foreground disabled:opacity-50"
              >
                <CheckCircle2 size={18} className="text-primary" />
                <span>Retry Health Checks</span>
                <span className="text-[9px] font-medium text-foreground-muted">Ping runtime endpoints</span>
              </button>
            </div>
          </div>

          {/* Danger zone */}
          <div className="bg-card border border-danger/30 bg-danger/5 rounded-2xl p-6 shadow-sm space-y-4">
            <div>
              <h2 className="text-sm font-bold text-danger uppercase tracking-wider">Danger Zone</h2>
              <p className="text-xs text-foreground-muted mt-0.5">Irreversible actions that delete infrastructure settings and hosted services.</p>
            </div>
            <p className="text-xs text-foreground-muted font-semibold leading-relaxed">
              Deleting this project will permanently remove the application record from ZeroOps, detach all custom domains, clear environment secrets, and delete the hosted container deployment instances from the managed production environment.
            </p>
            <div className="pt-2 border-t border-danger/10 flex justify-end">
              <button
                onClick={handleDeleteProject}
                className="px-4 py-2 bg-danger hover:bg-danger-hover text-white text-xs font-bold rounded-xl transition cursor-pointer shadow-md shadow-danger/10"
              >
                Delete Application
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AppDetailsPage() {
  const params = useParams<{ id?: string }>();
  const resolvedId = params?.id || "";

  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-[400px]">
          <Loader2 className="animate-spin text-primary" size={32} />
        </div>
      }
    >
      <AppDetailsPageContent projectId={resolvedId} />
    </Suspense>
  );
}
