"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  Bot,
  Check,
  Clock3,
  Copy,
  Database,
  ExternalLink,
  Layers3,
  Loader2,
  Mail,
  MessageSquare,
  Play,
  RefreshCw,
  Send,
  Server,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  api,
  getErrorMessage,
  type EphemeralResource,
  type EphemeralResourceProposal,
  type IntegrationSettings,
  type ResourceCatalog,
} from "@/lib/api";
import { useNotifications } from "@/lib/NotificationContext";

type Tab = "resources" | "chat" | "custom" | "integrations";
type ResourceFamily = "any" | "compute" | "containers" | "database" | "storage" | "networking" | "app-platform" | "ai-data" | "other";

interface ChatEntry {
  id: string;
  sender: "user" | "assistant";
  text: string;
  proposal?: EphemeralResourceProposal | null;
  resource?: EphemeralResource | null;
}

interface DeployProposal {
  proposal: EphemeralResourceProposal;
  armTemplate: Record<string, unknown>;
  armParameters: Record<string, unknown>;
  hourlyEstimate: number;
}

function parseJsonObject(value: string, label: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

function remainingLabel(seconds?: number) {
  if (!seconds || seconds <= 0) return "Expired";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}

function TemplatePlanCard({
  proposal,
  busy,
  onDeploy,
}: {
  proposal: EphemeralResourceProposal;
  busy: boolean;
  onDeploy: (input: DeployProposal) => Promise<void>;
}) {
  const [templateText, setTemplateText] = useState(JSON.stringify(proposal.arm_template ?? {}, null, 2));
  const [parametersText, setParametersText] = useState(JSON.stringify(proposal.arm_parameters ?? {}, null, 2));
  const [hourlyEstimate, setHourlyEstimate] = useState(String(proposal.estimated_resource_hourly_usd ?? ""));
  const [quote, setQuote] = useState<{ hourly_subtotal: number; total_subtotal: number } | null>(null);
  const [quoting, setQuoting] = useState(false);
  const [validationError, setValidationError] = useState("");

  const calculateQuote = async () => {
    const rate = Number(hourlyEstimate);
    if (!Number.isFinite(rate) || rate < 0) {
      setValidationError("Enter the hourly Azure estimate from your pricing calculator.");
      return;
    }
    setQuoting(true);
    setValidationError("");
    try {
      const next = await api.quoteCustomResource(rate, proposal.ttl_minutes);
      setQuote(next);
    } catch (error) {
      setValidationError(getErrorMessage(error, "Unable to calculate the subtotal."));
    } finally {
      setQuoting(false);
    }
  };

  const deploy = async () => {
    try {
      const armTemplate = parseJsonObject(templateText, "ARM template");
      const armParameters = parseJsonObject(parametersText, "ARM parameters");
      const rate = Number(hourlyEstimate);
      if (!Number.isFinite(rate) || rate < 0) throw new Error("Enter the hourly Azure estimate from your pricing calculator.");
      if (!quote) {
        await calculateQuote();
        return;
      }
      await onDeploy({ proposal, armTemplate, armParameters, hourlyEstimate: rate });
    } catch (error) {
      setValidationError(getErrorMessage(error, "Review the deployment details."));
    }
  };

  return (
    <div className="mt-4 rounded-2xl border border-primary/30 bg-primary-subtle/30 p-4 text-left">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="font-semibold text-foreground">Review Azure deployment plan</h4>
          <p className="mt-1 text-xs text-foreground-muted">{proposal.summary}</p>
        </div>
        <span className="rounded-full border border-border bg-card px-2.5 py-1 text-xs font-medium text-foreground-muted">
          {proposal.region} · {proposal.ttl_minutes} min TTL
        </span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="text-xs font-semibold text-foreground">
          Azure estimate (USD per hour)
          <input
            type="number"
            min="0"
            step="0.001"
            value={hourlyEstimate}
            onChange={(event) => {
              setHourlyEstimate(event.target.value);
              setQuote(null);
            }}
            className="mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm font-normal"
          />
        </label>
        <div className="rounded-xl border border-border bg-card p-3 text-xs">
          <p className="font-semibold text-foreground">All-inclusive subtotal</p>
          {quote ? (
            <p className="mt-2 font-mono text-sm text-emerald-500">
              ${quote.hourly_subtotal.toFixed(3)}/hr · ${quote.total_subtotal.toFixed(3)} for this TTL
            </p>
          ) : (
            <p className="mt-2 text-foreground-muted">Calculate after confirming the Azure estimate.</p>
          )}
          <button
            type="button"
            onClick={() => void calculateQuote()}
            disabled={quoting}
            className="mt-2 inline-flex min-h-9 items-center gap-2 rounded-lg border border-border px-3 font-semibold hover:bg-muted disabled:opacity-60"
          >
            {quoting ? <Loader2 size={14} className="animate-spin" /> : null}
            Calculate subtotal
          </button>
        </div>
      </div>

      <details className="mt-4" open>
        <summary className="cursor-pointer text-xs font-semibold text-foreground">ARM template and resource configuration</summary>
        <textarea
          aria-label="Azure Resource Manager template JSON"
          value={templateText}
          onChange={(event) => {
            setTemplateText(event.target.value);
            setQuote(null);
          }}
          rows={14}
          spellCheck={false}
          className="mt-2 w-full rounded-xl border border-border bg-background p-3 font-mono text-xs text-foreground"
        />
      </details>
      <details className="mt-3">
        <summary className="cursor-pointer text-xs font-semibold text-foreground">ARM parameter values</summary>
        <p className="mt-1 text-[11px] text-foreground-muted">Secret parameter values are used for this request and are not stored in resource history.</p>
        <textarea
          aria-label="Azure Resource Manager parameter values JSON"
          value={parametersText}
          onChange={(event) => setParametersText(event.target.value)}
          rows={5}
          spellCheck={false}
          className="mt-2 w-full rounded-xl border border-border bg-background p-3 font-mono text-xs text-foreground"
        />
      </details>
      {validationError ? <p role="alert" className="mt-3 text-xs text-danger">{validationError}</p> : null}
      <button
        type="button"
        onClick={() => void deploy()}
        disabled={busy || quoting}
        className="ops-primary mt-4 min-h-11 w-full justify-center"
      >
        {busy ? <Loader2 size={16} className="animate-spin" /> : <Play size={15} />}
        {busy ? "Waiting for Azure confirmation…" : "Deploy reviewed template"}
      </button>
    </div>
  );
}

export default function CloudSandboxPage() {
  const { addToast } = useNotifications();
  const [tab, setTab] = useState<Tab>("resources");
  const [resources, setResources] = useState<EphemeralResource[]>([]);
  const [catalog, setCatalog] = useState<ResourceCatalog | null>(null);
  const [integrations, setIntegrations] = useState<IntegrationSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [savingIntegrations, setSavingIntegrations] = useState(false);
  const [chatBusy, setChatBusy] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [chatRegion, setChatRegion] = useState("eastus");
  const [resourceFamily, setResourceFamily] = useState<ResourceFamily>("any");
  const [chatMessages, setChatMessages] = useState<ChatEntry[]>([
    {
      id: "welcome",
      sender: "assistant",
      text: "Describe the Azure resources your team needs and the AI will prepare a template for review. Include your Azure Pricing Calculator estimate, for example: `Azure estimate $0.12/hr`. Nothing is deployed until you review the template and choose Deploy.",
    },
  ]);
  const [customName, setCustomName] = useState("");
  const [customRegion, setCustomRegion] = useState("eastus");
  const [customSku, setCustomSku] = useState("Custom");
  const [customTtl, setCustomTtl] = useState(120);
  const [customEstimate, setCustomEstimate] = useState("");
  const [customTemplate, setCustomTemplate] = useState("");
  const [customParameters, setCustomParameters] = useState("{}");
  const [customQuote, setCustomQuote] = useState<{ hourly_subtotal: number; total_subtotal: number } | null>(null);
  const [jiraSecretInput, setJiraSecretInput] = useState("");
  const [jiraTokenInput, setJiraTokenInput] = useState("");
  const [emailSecretInput, setEmailSecretInput] = useState("");
  const [jiraProjects, setJiraProjects] = useState("QA, DEV, INFRA");
  const [allowedDomains, setAllowedDomains] = useState("");
  const [copiedKey, setCopiedKey] = useState("");

  const loadData = useCallback(async (quiet = false) => {
    if (!quiet) setRefreshing(true);
    try {
      const [resourceList, catalogData, settings] = await Promise.all([
        api.getEphemeralResources(),
        api.getResourceCatalog(),
        api.getIntegrationSettings().catch(() => null),
      ]);
      setResources(resourceList);
      setCatalog(catalogData);
      if (settings) {
        setIntegrations(settings);
        setJiraProjects(settings.jira.jira_project_keys.join(", "));
        setAllowedDomains(settings.email.allowed_domains.join(", "));
      }
    } catch (error) {
      addToast(getErrorMessage(error, "Unable to load Azure resources."), "error");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [addToast]);

  useEffect(() => {
    void loadData();
    const timer = window.setInterval(() => void loadData(true), 30000);
    return () => window.clearInterval(timer);
  }, [loadData]);

  const deployTemplate = async ({ proposal, armTemplate, armParameters, hourlyEstimate }: DeployProposal) => {
    setDeploying(true);
    try {
      const created = await api.createEphemeralResource({
        name: proposal.name,
        resource_type: "custom_arm",
        region: proposal.region,
        sku: proposal.sku,
        ttl_minutes: proposal.ttl_minutes,
        arm_template: armTemplate,
        arm_parameters: armParameters,
        estimated_resource_hourly_usd: hourlyEstimate,
        source: "ai_chat",
      });
      setResources((current) => [created, ...current]);
      setChatMessages((current) => [...current, {
        id: `deployed-${Date.now()}`,
        sender: "assistant",
        text: `Azure confirmed deployment of ${created.configuration.resource_count ?? 1} resource(s) in ${created.azure_resource_group}. The all-inclusive subtotal is $${created.cost_estimate_hourly.toFixed(3)}/hr. Auto-teardown is scheduled for ${new Date(created.expires_at).toLocaleString()}.`,
        resource: created,
      }]);
      addToast("Azure confirmed the resource deployment.", "success");
      setTab("resources");
    } catch (error) {
      addToast(getErrorMessage(error, "Azure did not confirm this deployment. Check Azure activity before retrying."), "error");
    } finally {
      setDeploying(false);
    }
  };

  const sendChat = async (event?: FormEvent, suggestion?: string) => {
    event?.preventDefault();
    const message = (suggestion ?? chatInput).trim();
    if (!message || chatBusy) return;
    setChatMessages((current) => [...current, { id: `user-${Date.now()}`, sender: "user", text: message }]);
    setChatInput("");
    setChatBusy(true);
    try {
      const plannerMessage = resourceFamily === "any"
        ? message
        : `Target Azure resource family: ${resourceFamily}.\nRequest: ${message}`;
      const response = await api.chatEphemeralResource(plannerMessage, undefined, false, chatRegion.trim());
      setChatMessages((current) => [...current, {
        id: `assistant-${Date.now()}`,
        sender: "assistant",
        text: response.reply,
        proposal: response.proposed_resource,
        resource: response.created_resource,
      }]);
    } catch (error) {
      addToast(getErrorMessage(error, "The resource planner could not complete this request."), "error");
    } finally {
      setChatBusy(false);
    }
  };

  const deployCustomTemplate = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const armTemplate = parseJsonObject(customTemplate, "ARM template");
      const armParameters = parseJsonObject(customParameters, "ARM parameters");
      const hourlyEstimate = Number(customEstimate);
      if (!Number.isFinite(hourlyEstimate) || hourlyEstimate < 0) throw new Error("Enter the hourly Azure estimate from your Azure Pricing Calculator.");
      setDeploying(true);
      const created = await api.createEphemeralResource({
        name: customName.trim() || "custom-azure-resource",
        resource_type: "custom_arm",
        region: customRegion,
        sku: customSku.trim() || "Custom",
        ttl_minutes: customTtl,
        arm_template: armTemplate,
        arm_parameters: armParameters,
        estimated_resource_hourly_usd: hourlyEstimate,
        source: "catalog_ui",
      });
      setResources((current) => [created, ...current]);
      setCustomQuote(null);
      addToast("Azure confirmed the resource deployment.", "success");
      setTab("resources");
    } catch (error) {
      addToast(getErrorMessage(error, "Review the template and Azure connection, then retry."), "error");
    } finally {
      setDeploying(false);
    }
  };

  const quoteCustom = async () => {
    const rate = Number(customEstimate);
    if (!Number.isFinite(rate) || rate < 0) {
      addToast("Enter an Azure hourly estimate first.", "error");
      return;
    }
    try {
      const quote = await api.quoteCustomResource(rate, customTtl);
      setCustomQuote(quote);
    } catch (error) {
      addToast(getErrorMessage(error, "Unable to calculate the subtotal."), "error");
    }
  };

  const destroyResource = async (resource: EphemeralResource) => {
    if (!window.confirm(`Delete the Azure resources created by ${resource.name}?`)) return;
    try {
      const deleted = await api.deleteEphemeralResource(resource.id);
      setResources((current) => current.map((item) => item.id === deleted.id ? deleted : item));
      addToast("Azure confirmed resource deletion.", "success");
    } catch (error) {
      addToast(getErrorMessage(error, "Azure has not confirmed deletion; the resource remains scheduled for teardown retry."), "error");
    }
  };

  const extendResource = async (resource: EphemeralResource) => {
    try {
      const updated = await api.extendEphemeralResource(resource.id, 60);
      setResources((current) => current.map((item) => item.id === updated.id ? updated : item));
      addToast("Resource lifetime extended by one hour.", "success");
    } catch (error) {
      addToast(getErrorMessage(error, "Unable to extend the Azure resource lifetime."), "error");
    }
  };

  const saveIntegrations = async (event: FormEvent) => {
    event.preventDefault();
    if (!integrations) return;
    if (integrations.jira.jira_enabled && !jiraSecretInput && !integrations.jira.jira_webhook_secret) {
      addToast("Set a Jira webhook HMAC secret before enabling Jira.", "error");
      return;
    }
    if (integrations.email.email_enabled && !emailSecretInput && !integrations.email.email_webhook_secret) {
      addToast("Set an inbound email bearer secret before enabling email requests.", "error");
      return;
    }
    setSavingIntegrations(true);
    try {
      const next = await api.updateIntegrationSettings({
        ...integrations,
        jira: {
          ...integrations.jira,
          jira_project_keys: jiraProjects.split(",").map((value) => value.trim().toUpperCase()).filter(Boolean),
          jira_api_token: jiraTokenInput || integrations.jira.jira_api_token,
          jira_webhook_secret: jiraSecretInput || integrations.jira.jira_webhook_secret,
        },
        email: {
          ...integrations.email,
          allowed_domains: allowedDomains.split(",").map((value) => value.trim().toLowerCase()).filter(Boolean),
          email_webhook_secret: emailSecretInput || integrations.email.email_webhook_secret,
        },
      });
      setIntegrations(next);
      setJiraSecretInput("");
      setJiraTokenInput("");
      setEmailSecretInput("");
      addToast("Integration settings saved.", "success");
    } catch (error) {
      addToast(getErrorMessage(error, "Unable to save integration settings."), "error");
    } finally {
      setSavingIntegrations(false);
    }
  };

  const copy = async (value: string, key: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedKey(key);
      window.setTimeout(() => setCopiedKey(""), 1800);
      addToast("Copied.", "success");
    } catch {
      addToast("Clipboard access was blocked by the browser.", "error");
    }
  };

  const activeResources = resources.filter((resource) => resource.status === "active");
  const activeHourlySubtotal = activeResources.reduce((total, resource) => total + (resource.hourly_subtotal ?? resource.cost_estimate_hourly), 0);
  const tabs: Array<{ id: Tab; label: string; icon: typeof Layers3 }> = [
    { id: "resources", label: "Resources", icon: Layers3 },
    { id: "chat", label: "AI request", icon: Bot },
    { id: "custom", label: "Custom ARM", icon: Server },
    { id: "integrations", label: "Integrations", icon: MessageSquare },
  ];

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        title="Azure resources"
        description="Request, customize, deploy, and automatically remove Azure resources within your verified customer resource group."
        actions={(
          <button type="button" onClick={() => void loadData()} disabled={refreshing} className="ops-secondary min-h-10">
            <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} /> Refresh
          </button>
        )}
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-border bg-card p-4">
          <p className="text-xs text-foreground-muted">Active resource sets</p>
          <p className="mt-1 text-2xl font-semibold text-foreground">{activeResources.length}</p>
        </div>
        <div className="rounded-2xl border border-border bg-card p-4">
          <p className="text-xs text-foreground-muted">Active all-inclusive subtotal</p>
          <p className="mt-1 font-mono text-2xl font-semibold text-foreground">${activeHourlySubtotal.toFixed(3)}<span className="text-sm font-normal text-foreground-muted">/hr</span></p>
        </div>
        <div className="rounded-2xl border border-border bg-card p-4">
          <p className="text-xs text-foreground-muted">Azure scope</p>
          <p className="mt-1 text-sm font-semibold text-foreground">Verified resource group only</p>
          <p className="mt-1 text-xs text-foreground-muted">Your Azure policies and RBAC remain in force.</p>
        </div>
      </div>

      <div className="flex gap-2 overflow-x-auto rounded-2xl border border-border bg-card p-2" role="tablist" aria-label="Azure resource tools">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            id={`tab-${id}`}
            type="button"
            role="tab"
            aria-selected={tab === id}
            aria-controls={`panel-${id}`}
            onClick={() => setTab(id)}
            className={`inline-flex min-h-11 shrink-0 items-center gap-2 rounded-xl px-4 text-sm font-semibold transition-colors ${tab === id ? "bg-primary text-primary-foreground" : "text-foreground-muted hover:bg-muted hover:text-foreground"}`}
          >
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      {tab === "resources" && (
        <section id="panel-resources" role="tabpanel" aria-labelledby="tab-resources" className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-foreground">Your deployments</h2>
              <p className="text-sm text-foreground-muted">Azure operation state, TTL, management link, and all-inclusive estimate.</p>
            </div>
            <button type="button" onClick={() => setTab("custom")} className="ops-primary min-h-11"><Play size={15} /> New resource set</button>
          </div>
          {loading ? (
            <div className="rounded-2xl border border-border bg-card p-10 text-center text-sm text-foreground-muted"><Loader2 className="mx-auto mb-3 animate-spin" />Loading resources…</div>
          ) : resources.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border bg-card p-10 text-center">
              <Database size={27} className="mx-auto text-foreground-muted" />
              <h3 className="mt-3 font-semibold text-foreground">No Azure resource deployments yet</h3>
              <p className="mx-auto mt-1 max-w-lg text-sm text-foreground-muted">Use the AI request tab for a template draft or the custom ARM tab to submit your own template.</p>
            </div>
          ) : (
            <div className="grid gap-4 xl:grid-cols-2">
              {resources.map((resource) => (
                <article key={resource.id} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-foreground">{resource.name}</h3>
                        <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold capitalize ${resource.status === "active" ? "bg-emerald-500/10 text-emerald-600" : resource.status === "failed" ? "bg-danger/10 text-danger" : "bg-muted text-foreground-muted"}`}>
                          {resource.status}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-foreground-muted">{resource.status === "unverified" ? "Legacy entry · Azure status unknown" : `${resource.configuration.resource_count ?? 1} resource(s) · ${resource.sku} · ${resource.region}`}</p>
                    </div>
                    <span className="rounded-lg bg-muted px-2.5 py-1 text-xs capitalize text-foreground-muted">{resource.source}</span>
                  </div>
                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
                    <div className="rounded-xl bg-muted/50 p-3">
                      <p className="text-[11px] text-foreground-muted">Resource group</p>
                      <p className="mt-1 truncate text-sm font-medium text-foreground">{resource.azure_resource_group || "—"}</p>
                    </div>
                    <div className="rounded-xl bg-muted/50 p-3">
                      <p className="text-[11px] text-foreground-muted">All-inclusive subtotal</p>
                      <p className="mt-1 font-mono text-sm font-semibold text-foreground">{resource.status === "unverified" ? "Unverified" : `$${(resource.hourly_subtotal ?? resource.cost_estimate_hourly).toFixed(3)}/hr`}</p>
                    </div>
                    <div className="rounded-xl bg-muted/50 p-3">
                      <p className="text-[11px] text-foreground-muted">Auto-teardown</p>
                      <p className="mt-1 flex items-center gap-1 text-sm font-medium text-foreground"><Clock3 size={13} /> {resource.status === "active" ? remainingLabel(resource.time_remaining_seconds) : resource.destroyed_at ? new Date(resource.destroyed_at).toLocaleString() : "—"}</p>
                    </div>
                  </div>
                  {resource.logs?.length ? (
                    <details className="mt-4">
                      <summary className="cursor-pointer text-xs font-semibold text-foreground">Azure deployment activity</summary>
                      <ul className="mt-2 space-y-2 border-l border-border pl-3 text-xs text-foreground-muted">
                        {resource.logs.map((entry, index) => <li key={`${entry.timestamp}-${index}`}>{entry.message}</li>)}
                      </ul>
                    </details>
                  ) : null}
                  <div className="mt-4 flex flex-wrap gap-2 border-t border-border pt-4">
                    {resource.connection_info.portal_url ? (
                      <a href={resource.connection_info.portal_url} target="_blank" rel="noreferrer" className="ops-secondary min-h-10"><ExternalLink size={14} /> Open Azure</a>
                    ) : null}
                    {resource.status === "active" ? (
                      <>
                        <button type="button" onClick={() => void extendResource(resource)} className="ops-secondary min-h-10">+1 hour</button>
                        <button type="button" onClick={() => void destroyResource(resource)} className="ops-secondary min-h-10 border-danger/30 text-danger"><Trash2 size={14} /> Delete Azure resources</button>
                      </>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      {tab === "chat" && (
        <section id="panel-chat" role="tabpanel" aria-labelledby="tab-chat" className="grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.7fr)]">
          <div className="rounded-2xl border border-border bg-card p-4 sm:p-6">
            <div className="flex items-center gap-3 border-b border-border pb-4">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-primary-subtle text-primary"><Bot size={19} /></span>
              <div><h2 className="font-semibold text-foreground">AI resource planner</h2><p className="text-xs text-foreground-muted">Creates a draft; deployment always requires your review.</p></div>
            </div>
            <div className="mt-4 max-h-[58vh] space-y-4 overflow-y-auto pr-1">
              {chatMessages.map((message) => (
                <div key={message.id} className={`max-w-3xl rounded-2xl p-4 ${message.sender === "user" ? "ml-auto bg-primary text-primary-foreground" : "border border-border bg-background text-foreground"}`}>
                  <div className="mb-2 flex items-center gap-2 text-xs font-semibold opacity-80">{message.sender === "user" ? <MessageSquare size={13} /> : <Bot size={13} />}{message.sender === "user" ? "You" : "ZeroOps AI"}</div>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.text}</p>
                  {message.proposal ? <TemplatePlanCard proposal={message.proposal} busy={deploying} onDeploy={deployTemplate} /> : null}
                  {message.resource?.connection_info.portal_url ? <a className="mt-3 inline-flex items-center gap-1 text-sm font-semibold underline" href={message.resource.connection_info.portal_url} target="_blank" rel="noreferrer">Open Azure deployment <ExternalLink size={13} /></a> : null}
                </div>
              ))}
              {chatBusy ? <div className="flex items-center gap-2 text-sm text-foreground-muted"><Loader2 size={15} className="animate-spin" /> Preparing and validating a draft…</div> : null}
            </div>
            <form onSubmit={(event) => void sendChat(event)} className="mt-4 space-y-2 border-t border-border pt-4">
              <div className="grid gap-2 sm:grid-cols-2">
                <label className="block text-xs font-semibold text-foreground">Resource family
                  <select value={resourceFamily} onChange={(event) => setResourceFamily(event.target.value as ResourceFamily)} aria-label="Choose Azure resource family" className="mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm font-normal">
                    <option value="any">Any Azure resource</option>
                    <option value="compute">Compute (VMs, disks, scale sets)</option>
                    <option value="containers">Containers (Container Apps, AKS, registry)</option>
                    <option value="database">Databases (Azure SQL, PostgreSQL, Cosmos DB)</option>
                    <option value="storage">Storage (accounts, files, queues)</option>
                    <option value="networking">Networking (VNets, load balancers, firewalls)</option>
                    <option value="app-platform">App platform (Web Apps, Functions)</option>
                    <option value="ai-data">AI and data (Azure AI, Search, analytics)</option>
                    <option value="other">Other Azure service</option>
                  </select>
                </label>
                <label className="block text-xs font-semibold text-foreground">Azure region ID
                  <input list="azure-region-options" value={chatRegion} onChange={(event) => setChatRegion(event.target.value.toLowerCase().replace(/\s+/g, ""))} aria-label="Choose Azure deployment region" placeholder="eastus2 or centralindia" className="mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm font-normal" />
                  <datalist id="azure-region-options">{catalog?.regions.map((region) => <option key={region.id} value={region.id} />)}</datalist>
                </label>
              </div>
              <div className="flex gap-2">
                <input value={chatInput} onChange={(event) => setChatInput(event.target.value)} aria-label="Describe Azure resource request" placeholder="Describe the resources and include an Azure estimate, e.g. $0.12/hr" className="min-h-11 min-w-0 flex-1 rounded-xl border border-border bg-background px-3 text-sm" />
                <button type="submit" disabled={chatBusy || !chatInput.trim()} aria-label="Send resource request" className="ops-primary min-h-11 min-w-11 justify-center"><Send size={16} /></button>
              </div>
            </form>
          </div>
          <aside className="space-y-4">
            <div className="rounded-2xl border border-border bg-card p-5">
              <h3 className="flex items-center gap-2 font-semibold text-foreground"><ShieldCheck size={17} className="text-emerald-500" /> Company guardrails</h3>
              <ul className="mt-3 space-y-2.5 text-sm text-foreground-muted">
                <li>Only a verified customer Azure resource group is used.</li>
                <li>Azure RBAC and Azure Policy remain authoritative.</li>
                <li>Privileged role assignments, policy changes, and nested deployments are blocked.</li>
                <li>Review every ARM resource and parameter before deployment.</li>
                <li>Resources are tracked against the request and scheduled for automatic deletion.</li>
              </ul>
            </div>
            <div className="rounded-2xl border border-border bg-card p-5">
              <h3 className="font-semibold text-foreground">Useful requests</h3>
              <div className="mt-3 space-y-2">
                {["Create an isolated Ubuntu VM with Docker for QA testing.", "Set up a test storage account in West Europe for 90 minutes.", "Deploy a PostgreSQL test server in East US for 3 hours."].map((suggestion) => (
                  <button key={suggestion} type="button" onClick={() => void sendChat(undefined, suggestion)} className="w-full rounded-xl border border-border p-3 text-left text-xs text-foreground-muted hover:border-primary/50 hover:text-foreground">{suggestion}</button>
                ))}
              </div>
              <p className="mt-3 text-[11px] text-foreground-muted">Examples create a plan only. Confirm pricing from your Azure account before deploying.</p>
            </div>
          </aside>
        </section>
      )}

      {tab === "custom" && (
        <section id="panel-custom" role="tabpanel" aria-labelledby="tab-custom" className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(280px,0.6fr)]">
          <form onSubmit={(event) => void deployCustomTemplate(event)} className="space-y-5 rounded-2xl border border-border bg-card p-5 sm:p-6">
            <div>
              <h2 className="font-semibold text-foreground">Custom Azure resource set</h2>
              <p className="mt-1 text-sm text-foreground-muted">Supply any supported ARM template for resources in your verified resource group. Templates are applied incrementally and tracked for exact teardown.</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="text-xs font-semibold text-foreground">Request name<input value={customName} onChange={(event) => setCustomName(event.target.value)} placeholder="qa-resource-set" className="mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm font-normal" /></label>
              <label className="text-xs font-semibold text-foreground">Azure region ID<input list="custom-azure-region-options" value={customRegion} onChange={(event) => setCustomRegion(event.target.value.toLowerCase().replace(/\s+/g, ""))} className="mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm font-normal" /><datalist id="custom-azure-region-options">{catalog?.regions.map((region) => <option key={region.id} value={region.id}>{region.label}</option>)}</datalist></label>
              <label className="text-xs font-semibold text-foreground">SKU / size description<input value={customSku} onChange={(event) => setCustomSku(event.target.value)} className="mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm font-normal" /></label>
              <label className="text-xs font-semibold text-foreground">Azure estimate (USD per hour)<input type="number" min="0" step="0.001" value={customEstimate} onChange={(event) => { setCustomEstimate(event.target.value); setCustomQuote(null); }} className="mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm font-normal" /></label>
            </div>
            <fieldset>
              <legend className="text-xs font-semibold text-foreground">Automatic teardown after</legend>
              <div className="mt-2 flex flex-wrap gap-2">{[60, 120, 240, 480, 1440, 2880].map((minutes) => <button key={minutes} type="button" onClick={() => { setCustomTtl(minutes); setCustomQuote(null); }} className={`min-h-10 rounded-xl border px-3 text-xs font-semibold ${customTtl === minutes ? "border-primary bg-primary text-primary-foreground" : "border-border text-foreground-muted hover:bg-muted"}`}>{minutes >= 60 ? `${minutes / 60}h` : `${minutes}m`}</button>)}</div>
            </fieldset>
            <label className="block text-xs font-semibold text-foreground">ARM template JSON<textarea required value={customTemplate} onChange={(event) => setCustomTemplate(event.target.value)} rows={16} spellCheck={false} placeholder={'{\n  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",\n  "contentVersion": "1.0.0.0",\n  "resources": []\n}'} className="mt-1.5 w-full rounded-xl border border-border bg-background p-3 font-mono text-xs font-normal" /></label>
            <label className="block text-xs font-semibold text-foreground">ARM parameter values<textarea value={customParameters} onChange={(event) => setCustomParameters(event.target.value)} rows={4} spellCheck={false} className="mt-1.5 w-full rounded-xl border border-border bg-background p-3 font-mono text-xs font-normal" /><span className="mt-1 block font-normal text-foreground-muted">Used for this deployment request; parameter values are not saved in resource history.</span></label>
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" onClick={() => void quoteCustom()} className="ops-secondary min-h-11">Calculate all-inclusive subtotal</button>
              {customQuote ? <span className="font-mono text-sm font-semibold text-emerald-500">${customQuote.hourly_subtotal.toFixed(3)}/hr · ${customQuote.total_subtotal.toFixed(3)} total</span> : null}
            </div>
            <button type="submit" disabled={deploying || !customTemplate.trim() || !customQuote} className="ops-primary min-h-11 w-full justify-center">
              {deploying ? <Loader2 size={16} className="animate-spin" /> : <Play size={15} />}
              {deploying ? "Waiting for Azure confirmation…" : "Deploy reviewed ARM template"}
            </button>
            <p className="text-xs text-foreground-muted">A quote is required before deployment. The resource subtotal includes platform operations and AI automation without itemizing either component.</p>
          </form>
          <aside className="space-y-4">
            <div className="rounded-2xl border border-border bg-card p-5">
              <h3 className="font-semibold text-foreground">Template guardrails</h3>
              <p className="mt-2 text-sm leading-relaxed text-foreground-muted">The template is limited to the connected resource group. ZeroOps blocks cross-scope deployments, deployment scripts, role assignments, policy assignments, and user-assigned identity creation. Azure Policy and RBAC can still reject a deployment.</p>
            </div>
            <div className="rounded-2xl border border-border bg-card p-5">
              <h3 className="font-semibold text-foreground">Pricing input</h3>
              <p className="mt-2 text-sm leading-relaxed text-foreground-muted">Azure pricing varies by service, region, usage, and agreement. Copy the hourly infrastructure estimate from your Azure Pricing Calculator; the quote returns one all-inclusive subtotal.</p>
            </div>
            <div className="rounded-2xl border border-border bg-card p-5">
              <h3 className="font-semibold text-foreground">Need a starting point?</h3>
              <p className="mt-2 text-sm text-foreground-muted">Ask the AI resource planner to draft a template, then review and edit it before deployment.</p>
              <button type="button" onClick={() => setTab("chat")} className="ops-secondary mt-3 min-h-10">Open AI planner <Bot size={14} /></button>
            </div>
          </aside>
        </section>
      )}

      {tab === "integrations" && integrations && (
        <section id="panel-integrations" role="tabpanel" aria-labelledby="tab-integrations" className="space-y-5">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Company request integrations</h2>
            <p className="text-sm text-foreground-muted">Tenant-bound callbacks, encrypted secrets, project/domain allowlists, and real deployment receipts.</p>
          </div>
          <form onSubmit={(event) => void saveIntegrations(event)} className="grid gap-5 xl:grid-cols-2">
            <div className="space-y-4 rounded-2xl border border-border bg-card p-5">
              <div className="flex items-center gap-2"><MessageSquare size={17} className="text-primary" /><h3 className="font-semibold text-foreground">Jira Cloud</h3></div>
              <label className="flex min-h-11 items-center gap-3 text-sm text-foreground"><input type="checkbox" checked={integrations.jira.jira_enabled} onChange={(event) => setIntegrations({ ...integrations, jira: { ...integrations.jira, jira_enabled: event.target.checked } })} />Enable signed Jira requests</label>
              <label className="block text-xs font-semibold text-foreground">Jira site URL<input value={integrations.jira.jira_host ?? ""} onChange={(event) => setIntegrations({ ...integrations, jira: { ...integrations.jira, jira_host: event.target.value } })} placeholder="https://company.atlassian.net" className="mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm font-normal" /></label>
              <label className="block text-xs font-semibold text-foreground">Jira service account email<input value={integrations.jira.jira_email ?? ""} onChange={(event) => setIntegrations({ ...integrations, jira: { ...integrations.jira, jira_email: event.target.value } })} className="mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm font-normal" /></label>
              <label className="block text-xs font-semibold text-foreground">Jira API token<input type="password" value={jiraTokenInput} onChange={(event) => setJiraTokenInput(event.target.value)} placeholder={integrations.jira.jira_api_token ? "Configured; leave empty to keep" : "Atlassian API token"} className="mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm font-normal" /></label>
              <label className="block text-xs font-semibold text-foreground">Webhook HMAC secret<input type="password" value={jiraSecretInput} onChange={(event) => setJiraSecretInput(event.target.value)} placeholder={integrations.jira.jira_webhook_secret ? "Configured; leave empty to keep" : "Use a long random secret"} className="mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm font-normal" /><span className="mt-1 block font-normal text-foreground-muted">The same secret must be set on the Jira webhook. Signature header: X-Hub-Signature (sha256).</span></label>
              <label className="block text-xs font-semibold text-foreground">Allowed project keys<input value={jiraProjects} onChange={(event) => setJiraProjects(event.target.value)} className="mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm font-normal" /><span className="mt-1 block font-normal text-foreground-muted">Comma-separated. Only these projects can trigger deployments.</span></label>
              <label className="flex min-h-11 items-center gap-3 text-sm text-foreground"><input type="checkbox" checked={integrations.jira.jira_auto_provision} onChange={(event) => setIntegrations({ ...integrations, jira: { ...integrations.jira, jira_auto_provision: event.target.checked } })} />Allow matching Jira tickets to provision</label>
              <div className="rounded-xl bg-muted/50 p-3">
                <p className="text-xs font-semibold text-foreground">Tenant webhook URL</p>
                <div className="mt-2 flex gap-2"><input readOnly value={integrations.webhook_url} className="min-w-0 flex-1 rounded-lg border border-border bg-background px-2 text-xs" /><button type="button" onClick={() => void copy(integrations.webhook_url, "jira")} aria-label="Copy Jira webhook URL" className="ops-secondary min-h-10 min-w-10 justify-center">{copiedKey === "jira" ? <Check size={14} /> : <Copy size={14} />}</button></div>
              </div>
            </div>

            <div className="space-y-4 rounded-2xl border border-border bg-card p-5">
              <div className="flex items-center gap-2"><Mail size={17} className="text-primary" /><h3 className="font-semibold text-foreground">Inbound developer email</h3></div>
              <label className="flex min-h-11 items-center gap-3 text-sm text-foreground"><input type="checkbox" checked={integrations.email.email_enabled} onChange={(event) => setIntegrations({ ...integrations, email: { ...integrations.email, email_enabled: event.target.checked } })} />Enable authenticated email requests</label>
              <label className="block text-xs font-semibold text-foreground">Request address<input value={integrations.email.inbound_email_address} onChange={(event) => setIntegrations({ ...integrations, email: { ...integrations.email, inbound_email_address: event.target.value } })} className="mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm font-normal" /></label>
              <label className="block text-xs font-semibold text-foreground">Allowed sender domains<input value={allowedDomains} onChange={(event) => setAllowedDomains(event.target.value)} placeholder="company.com, contractor.example" className="mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm font-normal" /><span className="mt-1 block font-normal text-foreground-muted">Comma-separated exact domains. No fallback account is used.</span></label>
              <label className="block text-xs font-semibold text-foreground">Maximum default lifetime<select value={integrations.email.default_ttl_minutes} onChange={(event) => setIntegrations({ ...integrations, email: { ...integrations.email, default_ttl_minutes: Number(event.target.value) } })} className="mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm font-normal">{[60, 120, 240, 480, 1440, 2880].map((ttl) => <option key={ttl} value={ttl}>{ttl >= 60 ? `${ttl / 60} hours` : `${ttl} minutes`}</option>)}</select></label>
              <label className="block text-xs font-semibold text-foreground">Inbound webhook bearer secret<input type="password" value={emailSecretInput} onChange={(event) => setEmailSecretInput(event.target.value)} placeholder={integrations.email.email_webhook_secret ? "Configured; leave empty to keep" : "Use a long random secret"} className="mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm font-normal" /><span className="mt-1 block font-normal text-foreground-muted">Keep this in your mail relay and send it as Authorization: Bearer &lt;secret&gt;.</span></label>
              <div className="rounded-xl bg-muted/50 p-3">
                <p className="text-xs font-semibold text-foreground">Normalized inbound JSON endpoint</p>
                <div className="mt-2 flex gap-2"><input readOnly value={integrations.inbound_email_url} className="min-w-0 flex-1 rounded-lg border border-border bg-background px-2 text-xs" /><button type="button" onClick={() => void copy(integrations.inbound_email_url, "email")} aria-label="Copy email webhook URL" className="ops-secondary min-h-10 min-w-10 justify-center">{copiedKey === "email" ? <Check size={14} /> : <Copy size={14} />}</button></div>
              </div>
              <p className="text-xs text-foreground-muted">The relay must verify the mailbox provider's signature, normalize its event to the documented JSON payload, then call this endpoint. ZeroOps validates the tenant bearer secret and sender domain.</p>
            </div>
            <div className="xl:col-span-2">
              <button type="submit" disabled={savingIntegrations} className="ops-primary min-h-11"><ShieldCheck size={15} />{savingIntegrations ? "Saving…" : "Save integration settings"}</button>
            </div>
          </form>
        </section>
      )}
      {tab === "integrations" && !integrations ? <div className="rounded-2xl border border-border bg-card p-8 text-center text-sm text-foreground-muted">Integration settings are unavailable.</div> : null}
    </div>
  );
}
