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
} from "@/lib/api";

const formatDateTime = (value?: string | null) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
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
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("overview");
  const [domainNameInput, setDomainNameInput] = useState("");
  const [addingDomain, setAddingDomain] = useState(false);
  const [verifyingDomain, setVerifyingDomain] = useState<string | null>(null);
  const [renewingSSL, setRenewingSSL] = useState<string | null>(null);
  const [redeploying, setRedeploying] = useState(false);

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

      const [depsData, metricsData, domainsData] = await Promise.allSettled([
        api.getDeployments(50),
        api.getProjectMetrics(projectId),
        api.getProjectDomains(projectId),
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

  const handleRedeploy = async () => {
    if (!project || redeploying) return;
    setRedeploying(true);
    addToast(`Redeploying ${project.name}...`, "info");
    try {
      const res = await api.startDeployment({
        project_id: project.id,
        branch: project.branch || "main",
        environment: latestDeployment?.environment || "production",
      });
      router.push(`/dashboard/deployments?id=${res.deployment_id}`);
    } catch {
      addToast("Failed to redeploy application.", "error");
    } finally {
      setRedeploying(false);
    }
  };

  const handleRollback = async () => {
    addToast("Rollback is not available for this application yet.", "warning");
  };

  const handleConnectDomain = async () => {
    if (!domainNameInput.trim() || !project) return;
    setAddingDomain(true);
    try {
      const updated = await api.connectDomain(project.id, domainNameInput.trim());
      setDomains(updated);
      setDomainNameInput("");
      addToast("Domain added. Complete DNS verification to go live.", "success");
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
      addToast("Domain verification updated.", "success");
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
      addToast("SSL renewal requested.", "success");
    } catch {
      addToast("Failed to renew SSL.", "error");
    } finally {
      setRenewingSSL(null);
    }
  };

  const domainStatus = (domain: CustomDomain) => {
    const connected = true;
    const secured = domain.ssl || domain.https_enabled;
    const live = domain.dns_verified && domain.https_enabled;
    return {
      connected: connected ? "Connected" : "Disconnected",
      secured: secured ? "Secured" : "Pending",
      live: live ? "Live" : "Pending",
    };
  };

  const performanceCards = [
    { label: "Response Time", value: metrics?.response_time || "—" },
    { label: "Availability", value: metrics?.uptime || "—" },
    { label: "Requests", value: metrics?.request_count ? metrics.request_count.toLocaleString() : "—" },
    { label: "Errors", value: metrics?.error_rate || "—" },
  ];

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "deployments", label: "Deployments" },
    { id: "logs", label: "Logs" },
    { id: "performance", label: "Performance" },
    { id: "domains", label: "Domains" },
  ];

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <p className="text-foreground-muted text-sm font-medium">Loading application dashboard...</p>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="bg-card border border-border rounded-2xl p-10 text-center">
        <p className="text-sm text-foreground">Application not found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3">
        <button
          onClick={() => router.push("/dashboard")}
          className="text-xs text-foreground-muted hover:text-foreground flex items-center gap-1"
        >
          <ArrowLeft size={14} /> Back to overview
        </button>
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-extrabold text-foreground">{project.name}</h1>
            <p className="text-xs text-foreground-muted">{project.full_name}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => liveUrl && window.open(liveUrl, "_blank")}
              disabled={!liveUrl}
              className="px-4 py-2 bg-primary text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition disabled:opacity-50"
            >
              <ExternalLink size={14} className="inline mr-1" /> Open App
            </button>
            <button
              onClick={handleRedeploy}
              disabled={redeploying}
              className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition"
            >
              <RefreshCw size={14} className="inline mr-1" /> Redeploy
            </button>
            <button
              onClick={handleRollback}
              className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition"
            >
              <RotateCcw size={14} className="inline mr-1" /> Rollback
            </button>
            <button
              onClick={() => handleTabChange("logs")}
              className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition"
            >
              <Terminal size={14} className="inline mr-1" /> View Logs
            </button>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-border/40 pb-3">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => handleTabChange(tab.id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
              activeTab === tab.id
                ? "bg-primary/10 text-primary"
                : "text-foreground-muted hover:text-foreground hover:bg-card-hover"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "overview" && (
        <div className="grid md:grid-cols-2 gap-6">
          <div className="bg-card border border-border rounded-2xl p-6 space-y-3">
            <h2 className="text-sm font-bold text-foreground">Overview</h2>
            <div className="grid grid-cols-2 gap-4 text-xs">
              <div>
                <p className="text-[10px] uppercase text-foreground-muted font-semibold">Environment</p>
                <p className="font-semibold text-foreground">{latestDeployment?.environment || "—"}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase text-foreground-muted font-semibold">Status</p>
                <p className="font-semibold text-foreground">{project.status || "—"}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase text-foreground-muted font-semibold">Live URL</p>
                <p className="font-semibold text-foreground truncate">{liveUrl || "Not available"}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase text-foreground-muted font-semibold">Latest Deployment</p>
                <p className="font-semibold text-foreground">{formatDateTime(latestDeployment?.completed_at || latestDeployment?.started_at)}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase text-foreground-muted font-semibold">Last Commit</p>
                <p className="font-semibold text-foreground">{latestDeployment?.commit_sha || "Not recorded"}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase text-foreground-muted font-semibold">Response Time</p>
                <p className="font-semibold text-foreground">{metrics?.response_time || "—"}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase text-foreground-muted font-semibold">Availability</p>
                <p className="font-semibold text-foreground">{metrics?.uptime || "—"}</p>
              </div>
            </div>
          </div>

          <div className="bg-card border border-border rounded-2xl p-6 space-y-3">
            <h2 className="text-sm font-bold text-foreground">Latest Deployment</h2>
            {latestDeployment ? (
              <div className="space-y-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-foreground-muted">Status</span>
                  <span className="font-semibold text-foreground">{latestDeployment.status}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-foreground-muted">Duration</span>
                  <span className="font-semibold text-foreground">{latestDeployment.duration || "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-foreground-muted">Deployed By</span>
                  <span className="font-semibold text-foreground">{latestDeployment.deployed_by}</span>
                </div>
              </div>
            ) : (
              <p className="text-xs text-foreground-muted">No deployments recorded yet.</p>
            )}
          </div>
        </div>
      )}

      {activeTab === "deployments" && (
        <div className="bg-card border border-border rounded-2xl p-6">
          {deployments.length === 0 ? (
            <p className="text-xs text-foreground-muted">No deployments recorded yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-foreground-muted border-b border-border">
                    <th className="text-left py-2">Version</th>
                    <th className="text-left py-2">Status</th>
                    <th className="text-left py-2">Environment</th>
                    <th className="text-left py-2">Started</th>
                    <th className="text-left py-2">Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {deployments.map((deployment) => (
                    <tr key={deployment.id} className="border-b border-border/40">
                      <td className="py-2 font-mono">{deployment.version || "—"}</td>
                      <td className="py-2 font-semibold">{deployment.status}</td>
                      <td className="py-2">{deployment.environment}</td>
                      <td className="py-2">{formatDateTime(deployment.started_at)}</td>
                      <td className="py-2">{deployment.duration || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === "logs" && (
        <div className="bg-card border border-border rounded-2xl p-6">
          <h2 className="text-sm font-bold text-foreground mb-3">Live Logs</h2>
          <div className="font-mono text-[11px] leading-6 h-[280px] overflow-y-auto no-scrollbar bg-zinc-950 text-zinc-100 rounded-xl p-4">
            {latestDeploymentDetail?.logs?.length ? (
              latestDeploymentDetail.logs.map((log, index) => (
                <p key={index} className={log.level === "ERROR" ? "text-red-400" : log.level === "WARN" ? "text-amber-400" : "text-zinc-300"}>
                  <span className="text-zinc-500 mr-2">[{log.timestamp ? log.timestamp.split("T")[1]?.slice(0, 8) : ""}]</span>
                  <span className="text-primary-light mr-1">[{log.level}]</span>
                  {log.message}
                </p>
              ))
            ) : (
              <p className="text-zinc-500">No logs recorded for this application yet.</p>
            )}
          </div>
        </div>
      )}

      {activeTab === "performance" && (
        <div className="grid md:grid-cols-4 gap-4">
          {performanceCards.map((card) => (
            <div key={card.label} className="bg-card border border-border rounded-2xl p-5 shadow-sm">
              <p className="text-[10px] uppercase text-foreground-muted font-semibold">{card.label}</p>
              <p className="text-xl font-bold text-foreground mt-2">{card.value}</p>
            </div>
          ))}
        </div>
      )}

      {activeTab === "domains" && (
        <div className="space-y-6">
          <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
            <h2 className="text-sm font-bold text-foreground">Connect a custom domain</h2>
            <div className="flex flex-col sm:flex-row gap-3">
              <input
                type="text"
                value={domainNameInput}
                onChange={(e) => setDomainNameInput(e.target.value)}
                placeholder="app.yourdomain.com"
                className="flex-1 bg-background-secondary border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:border-primary focus:outline-none"
              />
              <button
                onClick={handleConnectDomain}
                disabled={addingDomain}
                className="px-4 py-2 bg-primary text-white rounded-lg text-xs font-semibold hover:bg-primary-hover transition disabled:opacity-50"
              >
                {addingDomain ? "Connecting..." : "Connect Domain"}
              </button>
            </div>
          </div>

          <div className="bg-card border border-border rounded-2xl p-6">
            <h2 className="text-sm font-bold text-foreground mb-4">Domains</h2>
            {domains.length === 0 ? (
              <p className="text-xs text-foreground-muted">No custom domains connected yet.</p>
            ) : (
              <div className="space-y-4">
                {domains.map((domain) => {
                  const status = domainStatus(domain);
                  return (
                    <div key={domain.name} className="border border-border rounded-xl p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Globe size={16} className="text-primary" />
                          <span className="font-semibold text-foreground text-sm">{domain.name}</span>
                        </div>
                        <div className="flex gap-2 text-[10px] font-semibold">
                          <span className="px-2 py-1 rounded-full bg-success/10 text-success">{status.connected}</span>
                          <span className="px-2 py-1 rounded-full bg-primary/10 text-primary">{status.secured}</span>
                          <span className="px-2 py-1 rounded-full bg-info/10 text-info">{status.live}</span>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button
                          onClick={() => handleVerifyDomain(domain.name)}
                          disabled={verifyingDomain === domain.name}
                          className="px-3 py-1.5 border border-border rounded-lg text-[10px] font-semibold hover:bg-card-hover transition"
                        >
                          {verifyingDomain === domain.name ? "Verifying..." : "Verify DNS"}
                        </button>
                        <button
                          onClick={() => handleRenewSSL(domain.name)}
                          disabled={renewingSSL === domain.name}
                          className="px-3 py-1.5 border border-border rounded-lg text-[10px] font-semibold hover:bg-card-hover transition"
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
