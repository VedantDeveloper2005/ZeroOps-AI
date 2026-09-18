"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  Bot,
  Check,
  CheckCircle2,
  Clock,
  Code2,
  Copy,
  Cpu,
  Database,
  Download,
  ExternalLink,
  Flame,
  Globe,
  HardDrive,
  Key,
  Layers,
  Loader2,
  Mail,
  MessageSquare,
  Play,
  Plus,
  Radio,
  RefreshCw,
  Send,
  Server,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Terminal,
  Trash2,
  Wand2,
  Zap,
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

type TabMode = "quick_launch" | "ai_chat" | "catalog" | "integrations";
type PersonaCategory = "all" | "testing" | "database" | "container" | "stress";

interface ChatEntry {
  id: string;
  sender: "user" | "assistant";
  text: string;
  proposal?: EphemeralResourceProposal | null;
  createdResource?: EphemeralResource | null;
  timestamp: string;
}

interface QuickPreset {
  id: string;
  name: string;
  title: string;
  description: string;
  badge: string;
  category: PersonaCategory;
  type: string;
  sku: string;
  distro: string;
  region: string;
  ttl: number;
  startupScript?: string;
  costPerHour: number;
}

const SMART_PRESETS: QuickPreset[] = [
  {
    id: "qa-runner",
    name: "qa-headless-runner",
    title: "QA Headless Test Runner",
    description: "Ubuntu 22.04 + Docker + Node.js 20 (2 vCPUs, 4GB RAM) for Cypress, Playwright & regression suites.",
    badge: "Most Popular",
    category: "testing",
    type: "vm_linux",
    sku: "Standard_B2s",
    distro: "Ubuntu 22.04 LTS",
    region: "eastus",
    ttl: 120,
    startupScript: "#!/bin/bash\ncurl -fsSL https://get.docker.com | sh && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt-get install -y nodejs",
    costPerHour: 0.068,
  },
  {
    id: "staging-postgres",
    name: "postgres-staging-db",
    title: "PostgreSQL 16 Staging DB",
    description: "Flexible Server, preconfigured 'testdb', SSL enforced (1 vCPU, 2GB RAM) for schema migrations.",
    badge: "Instant Database",
    category: "database",
    type: "database_postgres",
    sku: "Standard_B1ms",
    distro: "PostgreSQL 16",
    region: "eastus",
    ttl: 120,
    costPerHour: 0.063,
  },
  {
    id: "windows-qa",
    name: "windows-qa-desktop",
    title: "Windows Server Desktop QA",
    description: "Windows Server 2022 Datacenter with Remote Desktop (RDP) preconfigured for manual tester sessions.",
    badge: "Desktop QA",
    category: "testing",
    type: "vm_windows",
    sku: "Standard_B2s",
    distro: "Windows Server 2022 Datacenter",
    region: "eastus",
    ttl: 120,
    costPerHour: 0.119,
  },
  {
    id: "redis-fast",
    name: "redis-cache-sandbox",
    title: "Redis Micro Cache Sandbox",
    description: "In-memory Redis data store for temporary caching, queue benchmarks & session validation.",
    badge: "Micro Caching",
    category: "database",
    type: "redis_cache",
    sku: "Basic_C0",
    distro: "Redis 6.0",
    region: "eastus",
    ttl: 60,
    costPerHour: 0.048,
  },
  {
    id: "staging-mysql",
    name: "mysql-staging-db",
    title: "MySQL 8.0 Staging DB",
    description: "Fully managed MySQL 8 instance with test database, utf8mb4 charset, and instant root credentials.",
    badge: "Relational DB",
    category: "database",
    type: "database_mysql",
    sku: "Standard_B1ms",
    distro: "MySQL 8.0",
    region: "eastus",
    ttl: 120,
    costPerHour: 0.063,
  },
  {
    id: "container-app",
    name: "docker-python-api",
    title: "Docker & Python 3.12 API Box",
    description: "Ubuntu 22.04 with Docker Compose, Python 3.12, and FastAPI ready for containerized service tests.",
    badge: "Container App",
    category: "container",
    type: "container_app",
    sku: "Standard_B2s",
    distro: "Ubuntu 22.04 LTS",
    region: "eastus",
    ttl: 120,
    startupScript: "#!/bin/bash\napt-get update && apt-get install -y docker.io docker-compose python3-pip",
    costPerHour: 0.075,
  },
  {
    id: "stress-benchmark",
    name: "high-mem-benchmark",
    title: "High-Memory Stress Box",
    description: "4 vCPUs, 16GB RAM for heavy concurrency tests, load simulation, and load-runner agents.",
    badge: "Heavy Workload",
    category: "stress",
    type: "vm_linux",
    sku: "Standard_D4s_v5",
    distro: "Ubuntu 22.04 LTS",
    region: "eastus",
    ttl: 180,
    costPerHour: 0.144,
  },
];

export default function CloudSandboxPage() {
  const { addToast } = useNotifications();
  const [activeTab, setActiveTab] = useState<TabMode>("quick_launch");
  const [selectedPersona, setSelectedPersona] = useState<PersonaCategory>("all");
  const [resources, setResources] = useState<EphemeralResource[]>([]);
  const [catalog, setCatalog] = useState<ResourceCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Auto-Pilot Mode in AI Chat
  const [autoPilotChat, setAutoPilotChat] = useState(true);

  // Active resource connect & live terminal drawer
  const [connectResource, setConnectResource] = useState<EphemeralResource | null>(null);
  const [activeTerminalTab, setActiveTerminalTab] = useState<"credentials" | "live_terminal" | "security">("credentials");
  const [simulatedLogs, setSimulatedLogs] = useState<string[]>([]);
  const [terminalCommandInput, setTerminalCommandInput] = useState("");
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Presets loading
  const [launchingPresetId, setLaunchingPresetId] = useState<string | null>(null);

  // Chat state
  const [chatMessages, setChatMessages] = useState<ChatEntry[]>([
    {
      id: "intro",
      sender: "assistant",
      text: "⚡ **ZeroOps Autonomous Cloud Agent Ready.**\n\nI automatically provision verified Azure sandboxes with zero manual configuration. Type what you need—e.g.:\n\n• *\"Spin up an Ubuntu box with Docker for 2 hours\"*\n• *\"Need a test Postgres 16 database in East US\"*\n• *\"Deploy a Windows VM with RDP for QA testing\"*\n\nWith **Auto-Pilot ON**, I immediately allocate and launch the resource without asking you to fill out forms!",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  // Catalog Form state
  const [selectedType, setSelectedType] = useState("vm_linux");
  const [selectedRegion, setSelectedRegion] = useState("eastus");
  const [selectedSku, setSelectedSku] = useState("Standard_B2s");
  const [selectedDistro, setSelectedDistro] = useState("Ubuntu 22.04 LTS");
  const [ttlMinutes, setTtlMinutes] = useState(120);
  const [startupScriptChoice, setStartupScriptChoice] = useState("docker");
  const [customName, setCustomName] = useState("");
  const [provisioningBusy, setProvisioningBusy] = useState(false);

  // Integrations state
  const [integrationSettings, setIntegrationSettings] = useState<IntegrationSettings | null>(null);
  const [jiraKeyInput, setJiraKeyInput] = useState("QA-408");
  const [jiraSummaryInput, setJiraSummaryInput] = useState("Need test VM for checkout load testing");
  const [jiraTestingBusy, setJiraTestingBusy] = useState(false);
  const [jiraLastResult, setJiraLastResult] = useState<any>(null);

  const [emailSenderInput, setEmailSenderInput] = useState("developer@myfirm.com");
  const [emailSubjectInput, setEmailSubjectInput] = useState("Request for test Postgres DB for migrations");
  const [emailTestingBusy, setEmailTestingBusy] = useState(false);
  const [emailLastResult, setEmailLastResult] = useState<any>(null);

  const loadData = useCallback(async () => {
    try {
      const [resList, catData, intSettings] = await Promise.all([
        api.getEphemeralResources(),
        api.getResourceCatalog(),
        api.getIntegrationSettings().catch(() => null),
      ]);
      setResources(resList);
      setCatalog(catData);
      if (intSettings) setIntegrationSettings(intSettings);
    } catch (err) {
      addToast(getErrorMessage(err, "Failed to load cloud sandboxes"), "error");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [addToast]);

  useEffect(() => {
    void loadData();
    const interval = setInterval(() => {
      void api.getEphemeralResources().then(setResources).catch(() => {});
    }, 15000);
    return () => clearInterval(interval);
  }, [loadData]);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  const copyToClipboard = (text: string, keyId: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(keyId);
    setTimeout(() => setCopiedKey(null), 2000);
    addToast("Copied to clipboard!", "success");
  };

  // ── Download RDP file for 1-Click Windows connection ──
  const downloadRdpFile = (resource: EphemeralResource) => {
    const ip = resource.connection_info.public_ip || "127.0.0.1";
    const username = resource.connection_info.username || "azureuser";
    const rdpData = `full address:s:${ip}:3389\nprompt for credentials:i:1\nusername:s:${username}\nadministrative session:i:1\n`;
    const blob = new Blob([rdpData], { type: "application/x-rdp" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${resource.name}-${ip}.rdp`;
    a.click();
    URL.revokeObjectURL(url);
    addToast("Downloaded Remote Desktop (.rdp) file! Double-click to launch.", "success");
  };

  // ── Launch Preset (1-Click Instant) ──
  const handleLaunchPreset = async (preset: QuickPreset) => {
    setLaunchingPresetId(preset.id);
    try {
      const created = await api.createEphemeralResource({
        name: preset.name,
        resource_type: preset.type,
        region: preset.region,
        sku: preset.sku,
        ttl_minutes: preset.ttl,
        os_distro: preset.distro,
        startup_script: preset.startupScript,
        source: "smart_preset",
      });
      addToast(`🚀 ${preset.title} provisioned instantly! IP: ${created.connection_info.public_ip}`, "success");
      setResources((prev) => [created, ...prev]);
      initTerminalLogs(created);
      setConnectResource(created);
    } catch (err) {
      addToast(getErrorMessage(err, "Failed to launch preset"), "error");
    } finally {
      setLaunchingPresetId(null);
    }
  };

  // ── Send AI Chat Message ──
  const handleSendMessage = async (e?: FormEvent, messageOverride?: string) => {
    if (e) e.preventDefault();
    const textToSend = messageOverride || chatInput.trim();
    if (!textToSend || chatBusy) return;

    const userMsg: ChatEntry = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    setChatMessages((prev) => [...prev, userMsg]);
    if (!messageOverride) setChatInput("");
    setChatBusy(true);

    try {
      const res = await api.chatEphemeralResource(textToSend, undefined, autoPilotChat);
      const assistantMsg: ChatEntry = {
        id: `assistant-${Date.now()}`,
        sender: "assistant",
        text: res.reply,
        proposal: res.proposed_resource,
        createdResource: res.created_resource,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setChatMessages((prev) => [...prev, assistantMsg]);
      if (res.created_resource) {
        setResources((prev) => [res.created_resource!, ...prev]);
        addToast(`⚡ Auto-Pilot deployed ${res.created_resource.name}!`, "success");
        initTerminalLogs(res.created_resource);
        setConnectResource(res.created_resource);
      }
    } catch (err) {
      addToast(getErrorMessage(err, "Failed to process chat message"), "error");
    } finally {
      setChatBusy(false);
    }
  };

  // ── Deploy Proposal from Chat ──
  const handleDeployProposal = async (proposal: EphemeralResourceProposal) => {
    setProvisioningBusy(true);
    try {
      const created = await api.createEphemeralResource({
        name: proposal.name,
        resource_type: proposal.resource_type,
        region: proposal.region,
        sku: proposal.sku,
        ttl_minutes: proposal.ttl_minutes,
        os_distro: proposal.os_distro,
        startup_script: proposal.startup_script || undefined,
        open_ports: proposal.open_ports,
        source: "chat",
      });
      addToast(`Sandbox ${created.name} deployed successfully!`, "success");
      setResources((prev) => [created, ...prev]);

      setChatMessages((prev) => [
        ...prev,
        {
          id: `deploy-${Date.now()}`,
          sender: "assistant",
          text: `🎉 **${created.name}** is live! Public IP: \`${created.connection_info.public_ip}\`. Auto-teardown in ${created.ttl_minutes}m.`,
          createdResource: created,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
      initTerminalLogs(created);
      setConnectResource(created);
    } catch (err) {
      addToast(getErrorMessage(err, "Failed to deploy resource proposal"), "error");
    } finally {
      setProvisioningBusy(false);
    }
  };

  // ── Deploy from Catalog Form ──
  const handleDeployCatalog = async (e: FormEvent) => {
    e.preventDefault();
    setProvisioningBusy(true);

    let startupScript: string | undefined = undefined;
    if (startupScriptChoice === "docker") {
      startupScript = "#!/bin/bash\ncurl -fsSL https://get.docker.com | sh";
    } else if (startupScriptChoice === "node") {
      startupScript = "#!/bin/bash\ncurl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt-get install -y nodejs";
    } else if (startupScriptChoice === "python") {
      startupScript = "#!/bin/bash\napt-get update && apt-get install -y python3 python3-pip python3-venv";
    }

    try {
      const created = await api.createEphemeralResource({
        name: customName.trim() || `sandbox-${selectedType.replace("_", "-")}`,
        resource_type: selectedType,
        region: selectedRegion,
        sku: selectedSku,
        ttl_minutes: ttlMinutes,
        os_distro: selectedDistro,
        startup_script: startupScript,
        source: "catalog_ui",
      });
      addToast(`Sandbox ${created.name} deployed!`, "success");
      setResources((prev) => [created, ...prev]);
      setCustomName("");
      initTerminalLogs(created);
      setConnectResource(created);
    } catch (err) {
      addToast(getErrorMessage(err, "Failed to deploy sandbox"), "error");
    } finally {
      setProvisioningBusy(false);
    }
  };

  // ── Extend Resource ──
  const handleExtend = async (resourceId: string) => {
    try {
      const updated = await api.extendEphemeralResource(resourceId, 60);
      setResources((prev) => prev.map((r) => (r.id === resourceId ? updated : r)));
      addToast(`Extended ${updated.name} lifetime by +1 hour!`, "success");
    } catch (err) {
      addToast(getErrorMessage(err, "Failed to extend resource"), "error");
    }
  };

  // ── Destroy Resource ──
  const handleDestroy = async (resourceId: string) => {
    try {
      const destroyed = await api.deleteEphemeralResource(resourceId);
      setResources((prev) => prev.map((r) => (r.id === resourceId ? destroyed : r)));
      addToast(`Sandbox ${destroyed.name} destroyed and cloud allocations released.`, "success");
      if (connectResource?.id === resourceId) {
        setConnectResource(null);
      }
    } catch (err) {
      addToast(getErrorMessage(err, "Failed to destroy resource"), "error");
    }
  };

  // ── Purge Inactive Sandboxes ──
  const handlePurgeInactive = async () => {
    const inactive = resources.filter((r) => r.status !== "active");
    if (inactive.length === 0) {
      addToast("No inactive sandboxes to clean up.", "info");
      return;
    }
    for (const res of inactive) {
      void handleDestroy(res.id);
    }
    addToast(`Cleaned up ${inactive.length} expired sandbox(es).`, "success");
  };

  // ── Test Jira Sync ──
  const handleTestJira = async (customKey?: string, customSummary?: string) => {
    setJiraTestingBusy(true);
    setJiraLastResult(null);
    const key = customKey || jiraKeyInput;
    const summary = customSummary || jiraSummaryInput;
    try {
      const res = await api.testJiraSync({
        issue_key: key,
        summary: summary,
        description: `Please provision a test sandbox for ${key}`,
        labels: ["zeroops-sandbox"],
      });
      setJiraLastResult(res);
      addToast(`Jira ticket ${key} processed autonomously!`, "success");
      void loadData();
    } catch (err) {
      addToast(getErrorMessage(err, "Failed to test Jira webhook"), "error");
    } finally {
      setJiraTestingBusy(false);
    }
  };

  // ── Test Inbound Email ──
  const handleTestEmail = async (customSender?: string, customSubj?: string) => {
    setEmailTestingBusy(true);
    setEmailLastResult(null);
    const sender = customSender || emailSenderInput;
    const subj = customSubj || emailSubjectInput;
    try {
      const res = await api.testInboundEmail({
        from_email: sender,
        subject: subj,
        body_text: `Hi Ops team, please spin up test infrastructure for ${subj}. Need it for 2 hours. Thanks!`,
      });
      setEmailLastResult(res);
      addToast(`Inbound email processed and response delivered!`, "success");
      void loadData();
    } catch (err) {
      addToast(getErrorMessage(err, "Failed to test inbound email"), "error");
    } finally {
      setEmailTestingBusy(false);
    }
  };

  // ── Terminal Simulator Logs ──
  const initTerminalLogs = (res: EphemeralResource) => {
    const ip = res.connection_info.public_ip || "10.0.4.12";
    const port = res.connection_info.port || 22;
    setSimulatedLogs([
      `[ZeroOps SSH Agent] Establishing secure tunnel to ${res.name} (${ip}:${port})...`,
      `[ZeroOps SSH Agent] Azure Network Security Group verified: Port ${port} open.`,
      `[ZeroOps SSH Agent] Authenticated as ${res.connection_info.username || "azureuser"}. Session ACTIVE.`,
      `Linux sandbox-node 5.15.0-1049-azure #56-Ubuntu SMP PREEMPT x86_64`,
      `Type 'help' or click quick commands below to inspect this environment.`,
    ]);
  };

  const handleRunTerminalCommand = (cmd: string) => {
    const trimmed = cmd.trim();
    if (!trimmed || !connectResource) return;

    let output = "";
    const lower = trimmed.toLowerCase();
    const ip = connectResource.connection_info.public_ip || "10.0.4.12";

    if (lower === "uptime") {
      output = `19:28:44 up 18 min, 1 user, load average: 0.12, 0.08, 0.03`;
    } else if (lower.startsWith("ping")) {
      output = `64 bytes from ${ip}: icmp_seq=1 ttl=56 time=18.4 ms\n64 bytes from ${ip}: icmp_seq=2 ttl=56 time=19.1 ms\n--- ${ip} ping statistics ---\n2 packets transmitted, 2 received, 0% packet loss, time 1002ms`;
    } else if (lower.includes("docker")) {
      output = `CONTAINER ID   IMAGE          COMMAND                  CREATED         STATUS         PORTS                  NAMES\n8b71d9e23f01   postgres:16    "docker-entrypoint.s…"   12 minutes ago   Up 12 minutes  0.0.0.0:5432->5432/tcp staging-db`;
    } else if (lower.includes("free") || lower.includes("mem")) {
      output = `               total        used        free      shared  buff/cache   available\nMem:         4021248      482112     2891040       12040      648096     3318736\nSwap:              0           0           0`;
    } else if (lower.includes("df")) {
      output = `Filesystem     1K-blocks    Used Available Use% Mounted on\n/dev/root       30438180 3849120  26572676  13% /\ntmpfs            2010624       0   2010624   0% /dev/shm`;
    } else if (lower.includes("netstat")) {
      output = `Active Internet connections (only servers)\nProto Recv-Q Send-Q Local Address           Foreign Address         State\ntcp        0      0 0.0.0.0:${connectResource.connection_info.port || 22}         0.0.0.0:*               LISTEN`;
    } else if (lower === "help") {
      output = `Available quick test commands: uptime, ping, docker ps, free -m, df -h, netstat -tuln`;
    } else {
      output = `bash: ${trimmed}: command executed successfully (exit code 0)`;
    }

    setSimulatedLogs((prev) => [
      ...prev,
      `$ ${trimmed}`,
      output,
    ]);
    setTerminalCommandInput("");
  };

  const activeSandboxes = resources.filter((r) => r.status === "active");
  const totalBurnRate = activeSandboxes.reduce((sum, r) => sum + (r.cost_estimate_hourly || 0), 0);
  const expiringSoonCount = activeSandboxes.filter((r) => (r.time_remaining_seconds || 0) < 1800).length;

  const formatRemainingTime = (seconds?: number) => {
    if (seconds === undefined || seconds <= 0) return "Expired";
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (hrs > 0) return `${hrs}h ${mins}m`;
    return `${mins}m`;
  };

  const filteredPresets = SMART_PRESETS.filter((p) => {
    if (selectedPersona === "all") return true;
    return p.category === selectedPersona;
  });

  if (loading) {
    return (
      <div className="mx-auto flex min-h-[50vh] max-w-6xl items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-foreground-muted">Loading Cloud Sandboxes & Automation Hub…</p>
        </div>
      </div>
    );
  }

  const currentTypeConfig = catalog?.catalog[selectedType];

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      {/* Header */}
      <PageHeader
        eyebrow="Autonomous Cloud Ops"
        title="Zero-Touch Cloud Sandboxes"
        description="Instant on-demand test environments with zero manual steps. Provision via 1-Click AI Presets, Autonomous Chat, Jira Tickets, or Developer Emails with guaranteed auto-teardown."
        actions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setRefreshing(true);
                void loadData();
              }}
              disabled={refreshing}
              className="ops-secondary min-h-11 px-4 text-xs font-semibold"
            >
              <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />
              {refreshing ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        }
      />

      {/* Expiring Soon Alert Banner */}
      {expiringSoonCount > 0 && (
        <div className="flex items-center justify-between rounded-2xl border border-amber-500/30 bg-amber-500/10 px-5 py-3 text-xs text-amber-500 shadow-sm">
          <div className="flex items-center gap-2 font-medium">
            <Clock size={16} />
            <span>
              <strong>{expiringSoonCount} sandbox(es)</strong> are expiring in under 30 minutes. Auto-destruction will reclaim cloud allocations unless extended.
            </span>
          </div>
          <button
            type="button"
            onClick={() => {
              activeSandboxes.forEach((r) => {
                if ((r.time_remaining_seconds || 0) < 1800) void handleExtend(r.id);
              });
            }}
            className="rounded-lg bg-amber-500 px-3 py-1.5 font-bold text-black hover:bg-amber-400 transition-all shadow-sm"
          >
            Extend All Active (+1h)
          </button>
        </div>
      )}

      {/* Stats Bar with System Telemetry */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="rounded-2xl border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between text-foreground-muted">
            <span className="text-xs font-medium uppercase tracking-wider">Active Sandboxes</span>
            <Server size={16} className="text-primary" />
          </div>
          <p className="mt-2 text-2xl font-bold text-foreground">{activeSandboxes.length}</p>
          <span className="text-xs text-foreground-muted">Zero leftover resources</span>
        </div>

        <div className="rounded-2xl border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between text-foreground-muted">
            <span className="text-xs font-medium uppercase tracking-wider">Hourly Burn Subtotal</span>
            <Flame size={16} className="text-amber-500" />
          </div>
          <p className="mt-2 text-2xl font-bold text-foreground">${totalBurnRate.toFixed(3)}/hr</p>
          <span className="text-xs text-foreground-muted">All-inclusive subtotal</span>
        </div>

        <div className="rounded-2xl border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between text-foreground-muted">
            <span className="text-xs font-medium uppercase tracking-wider">Auto-Pilot Mode</span>
            <Wand2 size={16} className="text-indigo-400" />
          </div>
          <p className="mt-2 flex items-center gap-1.5 text-sm font-semibold text-indigo-400">
            <span className="h-2 w-2 rounded-full bg-indigo-400 animate-pulse" />
            Zero-Click Active
          </p>
          <span className="text-xs text-foreground-muted">Autonomous allocation</span>
        </div>

        <div className="rounded-2xl border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between text-foreground-muted">
            <span className="text-xs font-medium uppercase tracking-wider">Teardown Reaper</span>
            <ShieldCheck size={16} className="text-emerald-500" />
          </div>
          <p className="mt-2 flex items-center gap-1.5 text-sm font-semibold text-emerald-500">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            Active Daemon
          </p>
          <span className="text-xs text-foreground-muted">Automated zombie killer</span>
        </div>
      </div>

      {/* Tab Switcher */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border pb-3">
        <button
          type="button"
          onClick={() => setActiveTab("quick_launch")}
          className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all ${
            activeTab === "quick_launch"
              ? "bg-primary text-primary-foreground shadow-sm"
              : "bg-card text-foreground-muted hover:bg-card-hover hover:text-foreground border border-border"
          }`}
        >
          <Zap size={16} />
          1-Click Instant Launchers
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("ai_chat")}
          className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all ${
            activeTab === "ai_chat"
              ? "bg-primary text-primary-foreground shadow-sm"
              : "bg-card text-foreground-muted hover:bg-card-hover hover:text-foreground border border-border"
          }`}
        >
          <Bot size={16} />
          Autonomous AI Chat
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("catalog")}
          className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all ${
            activeTab === "catalog"
              ? "bg-primary text-primary-foreground shadow-sm"
              : "bg-card text-foreground-muted hover:bg-card-hover hover:text-foreground border border-border"
          }`}
        >
          <Layers size={16} />
          Custom Configurator
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("integrations")}
          className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all ${
            activeTab === "integrations"
              ? "bg-primary text-primary-foreground shadow-sm"
              : "bg-card text-foreground-muted hover:bg-card-hover hover:text-foreground border border-border"
          }`}
        >
          <ExternalLink size={16} />
          Jira & Email Zero-Touch
        </button>
      </div>

      {/* ── TAB 0: 1-CLICK INSTANT LAUNCHERS (ZERO MANUAL CONFIG) ── */}
      {activeTab === "quick_launch" && (
        <div className="space-y-5">
          {/* Proactive AI Recommendation Hero Card */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-3xl border border-primary/30 bg-gradient-to-r from-primary-subtle/70 via-background to-card p-5 shadow-sm">
            <div className="flex items-start gap-3.5">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-primary text-primary-foreground shadow-sm">
                <Sparkles size={20} />
              </span>
              <div>
                <span className="text-[11px] font-bold uppercase tracking-wider text-primary">
                  Proactive AI Workload Engine
                </span>
                <h3 className="text-sm font-bold text-foreground">
                  Recommended for your team: QA Headless Test Runner
                </h3>
                <p className="mt-0.5 text-xs text-foreground-muted max-w-xl">
                  Ubuntu 22.04 with Docker & Node.js 20 preinstalled. Auto-destroys in 2h to eliminate cloud waste.
                </p>
              </div>
            </div>
            <button
              type="button"
              disabled={launchingPresetId === "qa-runner"}
              onClick={() => handleLaunchPreset(SMART_PRESETS[0])}
              className="ops-primary shrink-0 px-5 py-2.5 text-xs font-bold shadow-md hover:scale-[1.02] transition-transform"
            >
              {launchingPresetId === "qa-runner" ? (
                <>
                  <Loader2 size={14} className="animate-spin" /> Launching…
                </>
              ) : (
                <>
                  <Play size={14} /> 1-Click Instant Deploy
                </>
              )}
            </button>
          </div>

          {/* Persona Filter Chips */}
          <div className="flex items-center justify-between flex-wrap gap-2 pt-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs font-bold uppercase text-foreground-muted mr-1">Filter by Persona:</span>
              {[
                { id: "all", label: "⚡ All Presets" },
                { id: "testing", label: "🧪 QA & E2E Testing" },
                { id: "database", label: "🗄️ Databases & Caches" },
                { id: "container", label: "🚀 Containers & Apps" },
                { id: "stress", label: "🔥 Performance Stress" },
              ].map((filter) => (
                <button
                  key={filter.id}
                  type="button"
                  onClick={() => setSelectedPersona(filter.id as PersonaCategory)}
                  className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition-all ${
                    selectedPersona === filter.id
                      ? "bg-foreground text-background shadow-sm"
                      : "border border-border bg-card text-foreground-muted hover:border-primary/50 hover:text-foreground"
                  }`}
                >
                  {filter.label}
                </button>
              ))}
            </div>

            <span className="text-xs text-foreground-muted font-medium">
              Showing {filteredPresets.length} pre-tuned sandboxes
            </span>
          </div>

          {/* Preset Cards Grid */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filteredPresets.map((preset) => {
              const isLaunching = launchingPresetId === preset.id;
              const Icon =
                preset.type === "database_postgres" || preset.type === "database_mysql"
                  ? Database
                  : preset.type === "redis_cache"
                  ? Radio
                  : preset.type === "vm_windows"
                  ? HardDrive
                  : preset.type === "container_app"
                  ? Layers
                  : Cpu;

              return (
                <div
                  key={preset.id}
                  className="flex flex-col justify-between rounded-3xl border border-border bg-card p-5 shadow-sm hover:border-primary/50 transition-all group hover:shadow-md"
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between">
                      <span className="grid h-10 w-10 place-items-center rounded-2xl bg-primary-subtle text-primary group-hover:scale-110 transition-transform">
                        <Icon size={20} />
                      </span>
                      <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-[11px] font-bold text-primary">
                        {preset.badge}
                      </span>
                    </div>

                    <div>
                      <h4 className="text-sm font-bold text-foreground">{preset.title}</h4>
                      <p className="mt-1 text-xs text-foreground-muted leading-relaxed">{preset.description}</p>
                    </div>

                    <div className="flex flex-wrap gap-1.5 pt-2 border-t border-border text-[11px] text-foreground-muted">
                      <span className="rounded-lg bg-muted px-2 py-0.5 font-medium">{preset.sku}</span>
                      <span className="rounded-lg bg-muted px-2 py-0.5 font-medium">{preset.region}</span>
                      <span className="rounded-lg bg-amber-500/10 text-amber-500 font-semibold px-2 py-0.5">
                        {preset.ttl / 60}h TTL
                      </span>
                      <span className="rounded-lg bg-emerald-500/10 text-emerald-500 font-bold px-2 py-0.5" title="All-inclusive subtotal">
                        ${preset.costPerHour}/hr Subtotal
                      </span>
                    </div>
                  </div>

                  <button
                    type="button"
                    disabled={isLaunching}
                    onClick={() => handleLaunchPreset(preset)}
                    className="ops-primary mt-5 w-full justify-center py-2.5 text-xs font-bold shadow-sm group-hover:bg-primary-hover"
                  >
                    {isLaunching ? (
                      <>
                        <Loader2 size={14} className="animate-spin" /> Allocating Cloud VM…
                      </>
                    ) : (
                      <>
                        <Play size={14} /> 1-Click Launch
                      </>
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── TAB 1: AUTONOMOUS CONVERSATIONAL AI CHAT ── */}
      {activeTab === "ai_chat" && (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="flex flex-col rounded-3xl border border-border bg-card shadow-sm lg:col-span-2 overflow-hidden">
            {/* Chat Header with Auto-Pilot Toggle */}
            <div className="flex items-center justify-between border-b border-border px-5 py-3.5 bg-muted/20">
              <div className="flex items-center gap-2.5">
                <span className="grid h-8 w-8 place-items-center rounded-xl bg-primary-subtle text-primary">
                  <Bot size={18} />
                </span>
                <div>
                  <h2 className="text-sm font-semibold text-foreground">ZeroOps Autonomous Cloud Agent</h2>
                  <p className="text-[11px] text-foreground-muted">Direct natural language to verified Azure sandboxes</p>
                </div>
              </div>

              {/* Auto-Pilot Mode Switch */}
              <label className="flex items-center gap-2 cursor-pointer rounded-xl bg-card px-3 py-1.5 border border-border shadow-sm hover:border-primary/50 transition-all">
                <input
                  type="checkbox"
                  checked={autoPilotChat}
                  onChange={(e) => setAutoPilotChat(e.target.checked)}
                  className="h-3.5 w-3.5 rounded text-primary focus:ring-primary cursor-pointer"
                />
                <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                  <Zap size={13} className={autoPilotChat ? "text-amber-500" : "text-foreground-muted"} />
                  Auto-Pilot (Zero Confirmation)
                </span>
              </label>
            </div>

            {/* Message Stream */}
            <div className="flex-1 space-y-4 overflow-y-auto p-5 max-h-[460px] min-h-[360px]">
              {chatMessages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex flex-col ${msg.sender === "user" ? "items-end" : "items-start"}`}
                >
                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                      msg.sender === "user"
                        ? "bg-primary text-primary-foreground rounded-br-none"
                        : "bg-muted/70 text-foreground border border-border rounded-bl-none"
                    }`}
                  >
                    <div className="whitespace-pre-wrap">{msg.text}</div>

                    {/* Proposal Card embedded in chat (when Auto-Pilot is OFF) */}
                    {msg.proposal && !msg.createdResource && (
                      <div className="mt-3 rounded-2xl border border-border bg-card p-3.5 text-foreground shadow-md">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold uppercase tracking-wider text-primary">
                            Proposed Infrastructure Plan
                          </span>
                          <span className="rounded bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary" title="All-inclusive subtotal">
                            Subtotal: ~${((msg.proposal.total_subtotal ?? (msg.proposal.cost_estimate_hourly * (msg.proposal.ttl_minutes / 60)))).toFixed(3)}
                          </span>
                        </div>

                        <div className="mt-2.5 grid grid-cols-2 gap-2 text-xs">
                          <div>
                            <span className="text-foreground-muted">Resource:</span>{" "}
                            <span className="font-medium text-foreground">{msg.proposal.name}</span>
                          </div>
                          <div>
                            <span className="text-foreground-muted">SKU:</span>{" "}
                            <span className="font-medium text-foreground">{msg.proposal.sku}</span>
                          </div>
                          <div>
                            <span className="text-foreground-muted">Region:</span>{" "}
                            <span className="font-medium text-foreground">{msg.proposal.region}</span>
                          </div>
                          <div>
                            <span className="text-foreground-muted">TTL Duration:</span>{" "}
                            <span className="font-semibold text-amber-500">{msg.proposal.ttl_minutes} mins</span>
                          </div>
                          <div className="col-span-2 pt-1 border-t border-border flex justify-between">
                            <span className="text-foreground-muted">Hourly Subtotal:</span>{" "}
                            <span className="font-semibold text-emerald-500">
                              ${(msg.proposal.hourly_subtotal ?? msg.proposal.cost_estimate_hourly).toFixed(3)}/hr
                            </span>
                          </div>
                        </div>

                        <button
                          type="button"
                          disabled={provisioningBusy}
                          onClick={() => handleDeployProposal(msg.proposal!)}
                          className="ops-primary mt-3 w-full justify-center py-2 text-xs font-semibold"
                        >
                          {provisioningBusy ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <Play size={14} />
                          )}
                          Approve & Deploy Sandbox
                        </button>
                      </div>
                    )}

                    {/* Instant Live Card when Auto-Pilot launched it */}
                    {msg.createdResource && (
                      <div className="mt-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-3.5 text-foreground">
                        <div className="flex items-center justify-between text-xs font-bold text-emerald-500">
                          <span className="flex items-center gap-1.5">
                            <CheckCircle2 size={14} /> Live Cloud Sandbox Active
                          </span>
                          <span>{msg.createdResource.sku}</span>
                        </div>
                        <div className="mt-2 text-xs font-mono bg-background/80 p-2.5 rounded-xl border border-border flex items-center justify-between">
                          <span className="truncate">{msg.createdResource.connection_info.ssh_command || msg.createdResource.connection_info.public_ip}</span>
                          <button
                            type="button"
                            onClick={() => copyToClipboard(msg.createdResource?.connection_info.ssh_command || msg.createdResource?.connection_info.public_ip || "", "chat-cmd")}
                            className="text-primary hover:text-primary-hover p-1"
                          >
                            <Copy size={13} />
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                  <span className="mt-1 px-1 text-[11px] text-foreground-muted">{msg.timestamp}</span>
                </div>
              ))}

              {chatBusy && (
                <div className="flex items-center gap-2 rounded-2xl bg-muted/50 p-3 text-xs text-foreground-muted max-w-[260px]">
                  <Loader2 size={14} className="animate-spin text-primary" />
                  {autoPilotChat ? "Auto-Pilot allocating Azure cloud sandbox…" : "Analyzing intent & sizing resources…"}
                </div>
              )}
              <div ref={chatBottomRef} />
            </div>

            {/* Zero-Typing Smart Action Pills */}
            <div className="border-t border-border p-3.5 space-y-2.5 bg-muted/10">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] font-bold uppercase text-foreground-muted mr-1 flex items-center gap-1">
                  <Sparkles size={11} className="text-primary" /> Instant Prompts:
                </span>
                {[
                  "🚀 Spin up Ubuntu 22.04 with Docker for 2 hours",
                  "🗄️ Need a test PostgreSQL 16 DB in East US",
                  "🖥️ Windows Server Desktop with RDP for QA testing",
                  "⚡ Redis in-memory cache for 1 hour",
                  "🔥 High-Memory Stress Box for benchmark",
                ].map((sugg, i) => (
                  <button
                    key={i}
                    type="button"
                    disabled={chatBusy}
                    onClick={() => handleSendMessage(undefined, sugg)}
                    className="rounded-xl border border-border bg-card px-2.5 py-1 text-xs text-foreground-muted hover:border-primary/50 hover:text-foreground transition-all shadow-xs"
                  >
                    {sugg}
                  </button>
                ))}
              </div>

              <form onSubmit={handleSendMessage} className="flex gap-2">
                <input
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder={autoPilotChat ? "Type your workload — Auto-Pilot allocates immediately with zero forms..." : "Ask for any VM, DB, or container..."}
                  disabled={chatBusy}
                  className="flex-1 rounded-xl border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-foreground-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <button
                  type="submit"
                  disabled={chatBusy || !chatInput.trim()}
                  className="ops-primary min-h-11 px-4"
                >
                  {chatBusy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                </button>
              </form>
            </div>
          </div>

          {/* Quick Guide / Best Practices Sidebar */}
          <div className="space-y-4">
            <div className="rounded-3xl border border-border bg-card p-5 shadow-sm space-y-3.5">
              <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
                <ShieldCheck size={16} className="text-emerald-500" />
                Zero-Touch Cloud Guardrails
              </h3>
              <p className="text-xs leading-relaxed text-foreground-muted">
                ZeroOps completely eliminates the slow DevOps ticket backlog while protecting your company from runaway cloud expenses.
              </p>
              <div className="space-y-2.5 pt-2 border-t border-border text-xs text-foreground-muted">
                <div className="flex items-start gap-2">
                  <span className="font-bold text-primary">•</span>
                  <span><strong>Zero Manual Typing:</strong> AI handles CPU sizing, RAM allocation, OS images, and NSG port opening automatically.</span>
                </div>
                <div className="flex items-start gap-2">
                  <span className="font-bold text-primary">•</span>
                  <span><strong>Guaranteed Auto-Teardown:</strong> Background reaper cleans up VMs/databases at expiration—no zombie cloud costs.</span>
                </div>
                <div className="flex items-start gap-2">
                  <span className="font-bold text-primary">•</span>
                  <span><strong>Direct Dev Integration:</strong> 1-click .RDP downloads, 1-click .env DATABASE_URL snippets, and interactive terminal console.</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 2: VISUAL SERVICE CATALOG DROPDOWNS ── */}
      {activeTab === "catalog" && (
        <div className="grid gap-6 lg:grid-cols-3">
          <form onSubmit={handleDeployCatalog} className="space-y-5 rounded-3xl border border-border bg-card p-6 shadow-sm lg:col-span-2">
            <div>
              <h3 className="text-base font-bold text-foreground">Custom Resource Configurator</h3>
              <p className="text-xs text-foreground-muted">For granular control: choose custom region, exact SKU, and custom startup sequences.</p>
            </div>

            {/* Resource Type Category Buttons */}
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-foreground-muted">Resource Category</label>
              <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {catalog &&
                  Object.entries(catalog.catalog).map(([key, item]) => {
                    const isSelected = selectedType === key;
                    return (
                      <button
                        key={key}
                        type="button"
                        onClick={() => {
                          setSelectedType(key);
                          setSelectedSku(item.default_sku);
                          if (item.distros && item.distros.length > 0) {
                            setSelectedDistro(item.distros[0].id);
                          }
                        }}
                        className={`flex flex-col items-start rounded-2xl border p-3 text-left transition-all ${
                          isSelected
                            ? "border-primary bg-primary-subtle text-primary shadow-sm"
                            : "border-border bg-background text-foreground-muted hover:border-border-hover hover:text-foreground"
                        }`}
                      >
                        <span className="text-xs font-bold text-foreground">{item.title}</span>
                        <span className="mt-1 text-[11px] text-foreground-muted truncate w-full">{item.category}</span>
                      </button>
                    );
                  })}
              </div>
            </div>

            {/* Region & SKU Row */}
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-foreground-muted">Azure Region</label>
                <select
                  value={selectedRegion}
                  onChange={(e) => setSelectedRegion(e.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm text-foreground focus:border-primary focus:outline-none"
                >
                  {catalog?.regions.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-foreground-muted">Instance SKU / Size</label>
                <select
                  value={selectedSku}
                  onChange={(e) => setSelectedSku(e.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm text-foreground focus:border-primary focus:outline-none"
                >
                  {currentTypeConfig?.skus.map((sku) => (
                    <option key={sku.id} value={sku.id}>
                      {sku.label} (~${sku.hourly_cost}/hr Subtotal)
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Distro / Engine & TTL Row */}
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-foreground-muted">OS / Engine Version</label>
                <select
                  value={selectedDistro}
                  onChange={(e) => setSelectedDistro(e.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm text-foreground focus:border-primary focus:outline-none"
                >
                  {currentTypeConfig?.distros.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-foreground-muted">Auto-Destroy TTL</label>
                <div className="mt-1.5 flex gap-1.5">
                  {[60, 120, 240, 480, 1440].map((mins) => (
                    <button
                      key={mins}
                      type="button"
                      onClick={() => setTtlMinutes(mins)}
                      className={`flex-1 rounded-xl border py-2 text-xs font-semibold transition-all ${
                        ttlMinutes === mins
                          ? "border-primary bg-primary text-primary-foreground shadow-sm"
                          : "border-border bg-background text-foreground-muted hover:text-foreground"
                      }`}
                    >
                      {mins >= 60 ? `${mins / 60}h` : `${mins}m`}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Custom Startup Script Preload (For VMs) */}
            {selectedType.startsWith("vm") && (
              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-foreground-muted">Preinstalled Packages (Cloud-Init)</label>
                <div className="mt-1.5 grid grid-cols-3 gap-2">
                  {[
                    { id: "docker", label: "Docker + Compose" },
                    { id: "node", label: "Node.js 20 LTS" },
                    { id: "python", label: "Python 3 + Pip" },
                  ].map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setStartupScriptChoice(startupScriptChoice === item.id ? "none" : item.id)}
                      className={`rounded-xl border p-2.5 text-xs font-medium transition-all text-center ${
                        startupScriptChoice === item.id
                          ? "border-primary bg-primary-subtle text-primary"
                          : "border-border bg-background text-foreground-muted hover:text-foreground"
                      }`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-foreground-muted">Sandbox Name (Optional)</label>
              <input
                type="text"
                value={customName}
                onChange={(e) => setCustomName(e.target.value)}
                placeholder={`e.g., qa-perf-${selectedType.replace("_", "-")}`}
                className="mt-1.5 w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm text-foreground focus:border-primary focus:outline-none"
              />
            </div>

            <button
              type="submit"
              disabled={provisioningBusy}
              className="ops-primary w-full justify-center py-3 text-sm font-bold shadow-md"
            >
              {provisioningBusy ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              {provisioningBusy ? "Allocating Cloud Resources…" : "Deploy Ephemeral Sandbox"}
            </button>
          </form>

          {/* Pricing & Summary Card */}
          <div className="space-y-4">
            <div className="rounded-3xl border border-border bg-card p-5 shadow-sm space-y-4">
              <h4 className="text-xs font-bold uppercase tracking-wider text-foreground-muted">Configuration Summary</h4>
              
              <div className="space-y-2.5 text-xs">
                <div className="flex justify-between py-1 border-b border-border">
                  <span className="text-foreground-muted">Type:</span>
                  <span className="font-semibold text-foreground">{currentTypeConfig?.title}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-border">
                  <span className="text-foreground-muted">SKU:</span>
                  <span className="font-semibold text-foreground">{selectedSku}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-border">
                  <span className="text-foreground-muted">Region:</span>
                  <span className="font-semibold text-foreground">{selectedRegion}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-border">
                  <span className="text-foreground-muted">Lifetime:</span>
                  <span className="font-semibold text-amber-500">{ttlMinutes / 60} hours</span>
                </div>
                <div className="flex justify-between py-1 border-b border-border">
                  <span className="text-foreground-muted">Hourly Subtotal:</span>
                  <span className="font-semibold text-foreground">
                    ${currentTypeConfig?.skus.find((s) => s.id === selectedSku)?.hourly_cost || 0.04}/hr
                  </span>
                </div>
                <div className="flex justify-between py-1 font-bold text-sm">
                  <span className="text-foreground">Estimated Subtotal:</span>
                  <span className="text-emerald-500">
                    ${((currentTypeConfig?.skus.find((s) => s.id === selectedSku)?.hourly_cost || 0.04) * (ttlMinutes / 60)).toFixed(3)}
                  </span>
                </div>
              </div>

              <div className="rounded-xl bg-muted/60 p-3 text-[11px] text-foreground-muted leading-relaxed">
                💡 <strong>All-Inclusive Subtotal:</strong> Includes resource compute/memory, automated platform operations, and AI intelligence in one consolidated subtotal. ZeroOps terminates this resource at the exact expiration timestamp.
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 3: JIRA & EMAIL-TO-CLOUD ZERO-TOUCH OPS ── */}
      {activeTab === "integrations" && (
        <div className="space-y-6">
          {/* Visual Automation Pipeline Banner */}
          <div className="rounded-3xl border border-border bg-card p-5 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold uppercase tracking-wider text-primary">Autonomous Integration Pipeline</span>
              <span className="text-xs font-bold text-emerald-500 flex items-center gap-1">
                <CheckCircle2 size={13} /> Active & Listening
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 text-center text-xs">
              <div className="rounded-2xl border border-border bg-background p-3">
                <span className="font-bold text-foreground">1. Intake</span>
                <p className="mt-1 text-[11px] text-foreground-muted">Jira Ticket or Dev Email received</p>
              </div>
              <div className="rounded-2xl border border-border bg-background p-3">
                <span className="font-bold text-primary">2. AI Intent Extraction</span>
                <p className="mt-1 text-[11px] text-foreground-muted">Parses OS, DB, CPU, RAM & TTL</p>
              </div>
              <div className="rounded-2xl border border-border bg-background p-3">
                <span className="font-bold text-amber-500">3. Azure Allocation</span>
                <p className="mt-1 text-[11px] text-foreground-muted">Provisions with strict TTL</p>
              </div>
              <div className="rounded-2xl border border-border bg-background p-3">
                <span className="font-bold text-emerald-500">4. Auto Reply & Teardown</span>
                <p className="mt-1 text-[11px] text-foreground-muted">Delivers credentials & auto-reaps</p>
              </div>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            {/* Jira Card */}
            <div className="rounded-3xl border border-border bg-card p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex items-center gap-2.5">
                  <span className="grid h-8 w-8 place-items-center rounded-xl bg-blue-500/10 text-blue-500 font-bold text-sm">
                    J
                  </span>
                  <div>
                    <h3 className="text-sm font-bold text-foreground">Jira Ticket Auto-Provisioning</h3>
                    <p className="text-xs text-foreground-muted">Zero-touch ticket webhook listener</p>
                  </div>
                </div>
                <span className="rounded-full bg-blue-500/10 px-2.5 py-0.5 text-xs font-semibold text-blue-500">
                  Fully Autonomous
                </span>
              </div>

              <p className="text-xs text-foreground-muted leading-relaxed">
                Connect your Jira project webhook. When developers file a ticket with the label <code className="text-primary font-mono font-semibold">zeroops-sandbox</code>, ZeroOps AI parses the request, deploys the Azure VM/DB, comments back with the IP, and destroys the resource upon ticket closure.
              </p>

              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-foreground-muted">Your Webhook Endpoint</label>
                <div className="mt-1.5 flex items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value={integrationSettings?.webhook_url || "https://api.zeroops.ai/api/integrations/jira/webhook"}
                    className="flex-1 rounded-xl border border-border bg-muted/40 px-3 py-2 text-xs font-mono text-foreground"
                  />
                  <button
                    type="button"
                    onClick={() => copyToClipboard(integrationSettings?.webhook_url || "", "jira-url")}
                    className="ops-secondary px-3 py-2 text-xs"
                  >
                    {copiedKey === "jira-url" ? <Check size={14} /> : <Copy size={14} />}
                  </button>
                </div>
              </div>

              {/* 1-Click Jira Simulators */}
              <div className="rounded-2xl border border-border bg-background p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                    <Play size={12} className="text-primary" /> 1-Click Ticket Simulation
                  </h4>
                  <span className="text-[10px] text-foreground-muted">Zero Typing Required</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <button
                    type="button"
                    disabled={jiraTestingBusy}
                    onClick={() => handleTestJira("QA-408", "Need test PostgreSQL 16 DB for schema migrations")}
                    className="rounded-xl border border-border bg-card p-2.5 text-left text-xs hover:border-primary/50 transition-all"
                  >
                    <span className="font-bold text-foreground flex items-center gap-1">
                      <Zap size={11} className="text-amber-500" /> QA-408
                    </span>
                    <p className="mt-0.5 text-[11px] text-foreground-muted truncate">PostgreSQL 16 Staging DB</p>
                  </button>

                  <button
                    type="button"
                    disabled={jiraTestingBusy}
                    onClick={() => handleTestJira("PERF-102", "Need Ubuntu VM with Docker for Cypress regression")}
                    className="rounded-xl border border-border bg-card p-2.5 text-left text-xs hover:border-primary/50 transition-all"
                  >
                    <span className="font-bold text-foreground flex items-center gap-1">
                      <Zap size={11} className="text-amber-500" /> PERF-102
                    </span>
                    <p className="mt-0.5 text-[11px] text-foreground-muted truncate">Ubuntu + Docker Test Runner</p>
                  </button>
                </div>

                {jiraLastResult && (
                  <div className="rounded-xl bg-card p-3 border border-border text-xs space-y-1.5 font-mono">
                    <p className="text-emerald-500 font-bold">✓ Ticket Processed: {jiraLastResult.status}</p>
                    <p className="text-foreground-muted text-[11px] whitespace-pre-wrap">
                      {jiraLastResult.generated_jira_comment}
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Email-to-Cloud Card */}
            <div className="rounded-3xl border border-border bg-card p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex items-center gap-2.5">
                  <span className="grid h-8 w-8 place-items-center rounded-xl bg-indigo-500/10 text-indigo-500 font-bold text-sm">
                    <Mail size={16} />
                  </span>
                  <div>
                    <h3 className="text-sm font-bold text-foreground">Inbound Email Provisioning Agent</h3>
                    <p className="text-xs text-foreground-muted">Developer emails to Azure resources in minutes</p>
                  </div>
                </div>
                <span className="rounded-full bg-indigo-500/10 px-2.5 py-0.5 text-xs font-semibold text-indigo-500">
                  Zero-Touch Email Agent
                </span>
              </div>

              <p className="text-xs text-foreground-muted leading-relaxed">
                When developers or testers email your firm's desk address, ZeroOps AI extracts requirements, allocates the Azure resource, and emails back a deployment report with SSH credentials and auto-destroy countdown.
              </p>

              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-foreground-muted">Inbound Desk Address</label>
                <div className="mt-1.5 flex items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value="sandbox@zeroops.ai"
                    className="flex-1 rounded-xl border border-border bg-muted/40 px-3 py-2 text-xs font-mono text-foreground"
                  />
                  <button
                    type="button"
                    onClick={() => copyToClipboard("sandbox@zeroops.ai", "email-addr")}
                    className="ops-secondary px-3 py-2 text-xs"
                  >
                    {copiedKey === "email-addr" ? <Check size={14} /> : <Copy size={14} />}
                  </button>
                </div>
              </div>

              {/* 1-Click Email Simulators */}
              <div className="rounded-2xl border border-border bg-background p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                    <Play size={12} className="text-primary" /> 1-Click Email Ingestion Simulation
                  </h4>
                  <span className="text-[10px] text-foreground-muted">Instant Ingestion</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <button
                    type="button"
                    disabled={emailTestingBusy}
                    onClick={() => handleTestEmail("dev@firm.com", "Request for test Redis micro cache for 1 hour")}
                    className="rounded-xl border border-border bg-card p-2.5 text-left text-xs hover:border-primary/50 transition-all"
                  >
                    <span className="font-bold text-foreground flex items-center gap-1">
                      <Zap size={11} className="text-indigo-400" /> Dev Request
                    </span>
                    <p className="mt-0.5 text-[11px] text-foreground-muted truncate">Redis Cache (1 Hour)</p>
                  </button>

                  <button
                    type="button"
                    disabled={emailTestingBusy}
                    onClick={() => handleTestEmail("tester@firm.com", "Need Windows Server VM with RDP for QA session")}
                    className="rounded-xl border border-border bg-card p-2.5 text-left text-xs hover:border-primary/50 transition-all"
                  >
                    <span className="font-bold text-foreground flex items-center gap-1">
                      <Zap size={11} className="text-indigo-400" /> QA Request
                    </span>
                    <p className="mt-0.5 text-[11px] text-foreground-muted truncate">Windows Desktop VM</p>
                  </button>
                </div>

                {emailLastResult && (
                  <div className="rounded-xl bg-card p-3 border border-border text-xs space-y-1 font-mono">
                    <p className="text-emerald-500 font-bold">✓ Email Replied: {emailLastResult.reply_subject}</p>
                    <p className="text-foreground-muted text-[11px]">Delivered to: {emailLastResult.recipient}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── ACTIVE & HISTORICAL CLOUD SANDBOXES ── */}
      <div className="space-y-4 pt-4 border-t border-border">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h3 className="text-base font-bold text-foreground">Active Sandboxes & Cloud Allocations</h3>
            <p className="text-xs text-foreground-muted">Live instances, auto-destruction countdowns, and 1-click developer connection strings</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handlePurgeInactive}
              className="rounded-xl border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground-muted hover:border-danger/40 hover:text-danger transition-all"
            >
              🧹 Purge Inactive
            </button>
            <span className="rounded-full border border-border bg-card px-3 py-1 text-xs font-semibold text-foreground-muted">
              {resources.length} Total Environments
            </span>
          </div>
        </div>

        {resources.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-border bg-card p-10 text-center space-y-3">
            <Server size={32} className="mx-auto text-primary" />
            <h4 className="text-sm font-bold text-foreground">No active sandboxes running</h4>
            <p className="text-xs text-foreground-muted max-w-sm mx-auto">
              Click any of the <strong>1-Click Smart Launchers</strong> above to immediately spin up an Azure sandbox with zero configuration!
            </p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {resources.map((res) => {
              const isActive = res.status === "active";
              const conn = res.connection_info || {};
              const remaining = res.time_remaining_seconds || 0;

              return (
                <div
                  key={res.id}
                  className={`flex flex-col justify-between rounded-3xl border bg-card p-5 shadow-sm transition-all ${
                    isActive ? "border-primary/40 hover:border-primary shadow-xs" : "border-border opacity-70"
                  }`}
                >
                  <div className="space-y-3">
                    {/* Top row */}
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2.5">
                        <span className="grid h-9 w-9 place-items-center rounded-2xl bg-primary-subtle text-primary">
                          {res.resource_type.includes("db") || res.resource_type.includes("postgres") || res.resource_type.includes("mysql") ? (
                            <Database size={16} />
                          ) : res.resource_type.includes("redis") ? (
                            <Radio size={16} />
                          ) : res.resource_type.includes("windows") ? (
                            <HardDrive size={16} />
                          ) : (
                            <Server size={16} />
                          )}
                        </span>
                        <div>
                          <h4 className="text-sm font-bold text-foreground truncate max-w-[160px]">{res.name}</h4>
                          <span className="text-[11px] text-foreground-muted">{res.sku} • {res.region}</span>
                        </div>
                      </div>

                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${
                          isActive
                            ? "bg-emerald-500/10 text-emerald-500"
                            : res.status === "destroying"
                            ? "bg-amber-500/10 text-amber-500"
                            : "bg-muted text-foreground-muted"
                        }`}
                      >
                        {res.status}
                      </span>
                    </div>

                    {/* Source tag, IP & Subtotal */}
                    <div className="grid grid-cols-2 gap-2 text-xs bg-muted/40 rounded-xl p-2.5">
                      <div>
                        <span className="text-foreground-muted block text-[10px] uppercase font-bold">Public Endpoint</span>
                        <span className="font-mono font-semibold text-foreground truncate block">{conn.public_ip || "Allocated"}</span>
                      </div>
                      <div className="text-right">
                        <span className="text-foreground-muted block text-[10px] uppercase font-bold">Hourly Subtotal</span>
                        <span className="font-mono font-semibold text-emerald-500 block">
                          ${(res.hourly_subtotal ?? res.cost_estimate_hourly).toFixed(3)}/hr
                        </span>
                      </div>
                    </div>

                    {/* Countdown / Auto-destroy bar */}
                    {isActive && (
                      <div className="space-y-1.5">
                        <div className="flex justify-between text-xs">
                          <span className="text-foreground-muted flex items-center gap-1">
                            <Clock size={12} /> Auto-Teardown:
                          </span>
                          <span className={`font-semibold ${remaining < 1800 ? "text-danger animate-pulse" : "text-amber-500"}`}>
                            {formatRemainingTime(remaining)}
                          </span>
                        </div>
                        <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                          <div
                            className={`h-full transition-all duration-1000 ${remaining < 1800 ? "bg-danger" : "bg-amber-500"}`}
                            style={{
                              width: `${Math.min(100, Math.max(5, (remaining / (res.ttl_minutes * 60)) * 100))}%`,
                            }}
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Action Buttons */}
                  <div className="mt-4 pt-3 border-t border-border flex items-center justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setConnectResource(res);
                        initTerminalLogs(res);
                        setActiveTerminalTab("credentials");
                      }}
                      className="ops-secondary flex-1 justify-center py-2 text-xs font-semibold"
                    >
                      <Terminal size={14} /> Quick Connect
                    </button>

                    {isActive && (
                      <>
                        <button
                          type="button"
                          onClick={() => handleExtend(res.id)}
                          title="Extend lifetime by +1 hour"
                          className="rounded-xl border border-border bg-card px-2.5 py-2 text-xs font-bold text-foreground hover:bg-card-hover hover:border-primary/50 transition-all"
                        >
                          +1h
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDestroy(res.id)}
                          title="Destroy immediately & reclaim cost"
                          className="rounded-xl border border-danger/30 bg-danger/10 p-2 text-danger hover:bg-danger/20 transition-all"
                        >
                          <Trash2 size={14} />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Connect & Live Terminal Drawer/Modal */}
      {connectResource && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-xl rounded-3xl border border-border bg-card p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2.5">
                <Terminal size={18} className="text-primary" />
                <div>
                  <h3 className="text-base font-bold text-foreground">{connectResource.name}</h3>
                  <p className="text-xs text-foreground-muted">{connectResource.sku} • {connectResource.region}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setConnectResource(null)}
                className="rounded-xl p-2 text-foreground-muted hover:bg-muted transition-colors"
              >
                ✕
              </button>
            </div>

            {/* Modal Tabs */}
            <div className="flex gap-2 border-b border-border pb-2">
              <button
                type="button"
                onClick={() => setActiveTerminalTab("credentials")}
                className={`text-xs font-semibold px-3 py-1.5 rounded-xl transition-all ${
                  activeTerminalTab === "credentials"
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-foreground-muted hover:text-foreground"
                }`}
              >
                1-Click Dev Snippets
              </button>
              <button
                type="button"
                onClick={() => setActiveTerminalTab("live_terminal")}
                className={`text-xs font-semibold px-3 py-1.5 rounded-xl transition-all ${
                  activeTerminalTab === "live_terminal"
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-foreground-muted hover:text-foreground"
                }`}
              >
                Live Web Terminal Simulator
              </button>
              <button
                type="button"
                onClick={() => setActiveTerminalTab("security")}
                className={`text-xs font-semibold px-3 py-1.5 rounded-xl transition-all ${
                  activeTerminalTab === "security"
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-foreground-muted hover:text-foreground"
                }`}
              >
                Security & NSG Rules
              </button>
            </div>

            {/* TAB 1: 1-CLICK DEV SNIPPETS */}
            {activeTerminalTab === "credentials" && (
              <div className="space-y-3.5 text-xs">
                {/* All-Inclusive Subtotal Rate Banner */}
                <div className="rounded-2xl border border-border bg-muted/30 p-3 flex items-center justify-between">
                  <div>
                    <span className="font-bold text-foreground block">Consolidated Burn Subtotal</span>
                    <span className="text-[11px] text-foreground-muted">Includes compute, platform lifecycle, and AI automation</span>
                  </div>
                  <span className="font-mono text-sm font-bold text-emerald-500">
                    ${(connectResource.hourly_subtotal ?? connectResource.cost_estimate_hourly).toFixed(3)}/hr
                  </span>
                </div>

                {/* Windows 1-Click RDP launcher */}
                {connectResource.resource_type.includes("windows") && (
                  <div className="rounded-2xl border border-blue-500/30 bg-blue-500/10 p-3.5 flex items-center justify-between">
                    <div>
                      <h4 className="font-bold text-foreground">Windows Remote Desktop Ready</h4>
                      <p className="text-[11px] text-foreground-muted">Download pre-configured .RDP connection shortcut</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => downloadRdpFile(connectResource)}
                      className="ops-primary px-3 py-2 text-xs font-bold shadow-sm flex items-center gap-1.5"
                    >
                      <Download size={14} /> Download .RDP
                    </button>
                  </div>
                )}

                <div>
                  <span className="text-foreground-muted uppercase font-bold text-[10px]">Public IP Endpoint</span>
                  <div className="mt-1 flex items-center gap-2">
                    <input
                      type="text"
                      readOnly
                      value={connectResource.connection_info.public_ip || ""}
                      className="flex-1 rounded-xl border border-border bg-muted/40 p-2 font-mono text-foreground"
                    />
                    <button
                      type="button"
                      onClick={() => copyToClipboard(connectResource.connection_info.public_ip || "", "ip")}
                      className="ops-secondary px-3 py-2"
                    >
                      {copiedKey === "ip" ? <Check size={14} /> : <Copy size={14} />}
                    </button>
                  </div>
                </div>

                {/* SSH Command for Linux */}
                {connectResource.connection_info.ssh_command && (
                  <div>
                    <span className="text-foreground-muted uppercase font-bold text-[10px]">SSH Terminal Command</span>
                    <div className="mt-1 flex items-center gap-2">
                      <input
                        type="text"
                        readOnly
                        value={connectResource.connection_info.ssh_command}
                        className="flex-1 rounded-xl border border-border bg-muted/40 p-2 font-mono text-foreground"
                      />
                      <button
                        type="button"
                        onClick={() => copyToClipboard(connectResource.connection_info.ssh_command || "", "ssh")}
                        className="ops-secondary px-3 py-2"
                      >
                        {copiedKey === "ssh" ? <Check size={14} /> : <Copy size={14} />}
                      </button>
                    </div>
                  </div>
                )}

                {/* Database Connection Strings & .env ready */}
                {connectResource.connection_info.connection_string && (
                  <div>
                    <span className="text-foreground-muted uppercase font-bold text-[10px]">Database URL (.env ready)</span>
                    <div className="mt-1 flex items-center gap-2">
                      <input
                        type="text"
                        readOnly
                        value={connectResource.connection_info.connection_string}
                        className="flex-1 rounded-xl border border-border bg-muted/40 p-2 font-mono text-foreground text-[11px]"
                      />
                      <button
                        type="button"
                        onClick={() => copyToClipboard(connectResource.connection_info.connection_string || "", "cs")}
                        className="ops-secondary px-3 py-2"
                      >
                        {copiedKey === "cs" ? <Check size={14} /> : <Copy size={14} />}
                      </button>
                    </div>
                  </div>
                )}

                {connectResource.connection_info.password && (
                  <div>
                    <span className="text-foreground-muted uppercase font-bold text-[10px]">Root / Admin Password</span>
                    <div className="mt-1 flex items-center gap-2">
                      <input
                        type="text"
                        readOnly
                        value={connectResource.connection_info.password}
                        className="flex-1 rounded-xl border border-border bg-muted/40 p-2 font-mono text-foreground"
                      />
                      <button
                        type="button"
                        onClick={() => copyToClipboard(connectResource.connection_info.password || "", "pwd")}
                        className="ops-secondary px-3 py-2"
                      >
                        {copiedKey === "pwd" ? <Check size={14} /> : <Copy size={14} />}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: LIVE WEB TERMINAL SIMULATOR */}
            {activeTerminalTab === "live_terminal" && (
              <div className="space-y-3">
                {/* Terminal Window */}
                <div className="rounded-2xl bg-black p-4 font-mono text-xs text-emerald-400 space-y-1.5 border border-border h-64 overflow-y-auto">
                  <div className="text-neutral-500 text-[11px] pb-1.5 border-b border-neutral-800 flex justify-between">
                    <span>Target: {connectResource.name} ({connectResource.connection_info.public_ip})</span>
                    <span className="text-emerald-400 font-bold flex items-center gap-1">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      CONNECTED (18ms)
                    </span>
                  </div>
                  {simulatedLogs.map((log, idx) => (
                    <p key={idx} className={log.startsWith("$") ? "text-amber-400 font-bold mt-2" : "text-slate-300"}>
                      {log}
                    </p>
                  ))}
                </div>

                {/* Interactive Quick Command Buttons */}
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[10px] font-bold uppercase text-foreground-muted mr-1">Quick Run:</span>
                  {[
                    "ping -c 2",
                    "uptime",
                    "docker ps",
                    "free -m",
                    "df -h",
                    "netstat -tuln",
                  ].map((cmd, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => handleRunTerminalCommand(cmd)}
                      className="rounded-lg border border-border bg-muted/40 px-2 py-1 text-[11px] font-mono text-foreground-muted hover:border-primary hover:text-foreground transition-all"
                    >
                      {cmd}
                    </button>
                  ))}
                </div>

                {/* Terminal Input */}
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={terminalCommandInput}
                    onChange={(e) => setTerminalCommandInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleRunTerminalCommand(terminalCommandInput);
                    }}
                    placeholder="Type bash command (e.g. uptime, docker ps, df -h)..."
                    className="flex-1 rounded-xl border border-border bg-background px-3 py-1.5 text-xs font-mono text-foreground focus:border-primary focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => handleRunTerminalCommand(terminalCommandInput)}
                    className="ops-primary px-3 py-1.5 text-xs font-semibold"
                  >
                    Run
                  </button>
                </div>
              </div>
            )}

            {/* TAB 3: SECURITY & NSG RULES */}
            {activeTerminalTab === "security" && (
              <div className="space-y-3 text-xs">
                <div className="rounded-2xl border border-border bg-background p-3.5 space-y-2">
                  <span className="font-bold text-foreground">Azure Network Security Group (NSG)</span>
                  <div className="space-y-1 text-foreground-muted text-[11px]">
                    <div className="flex justify-between py-1 border-b border-border">
                      <span>Inbound Port:</span>
                      <span className="font-mono font-bold text-foreground">{connectResource.connection_info.port || 22}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-border">
                      <span>Protocol:</span>
                      <span className="font-mono text-foreground">TCP</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-border">
                      <span>IP Whitelisting:</span>
                      <span className="text-emerald-500 font-semibold">Corporate Workspace IP Auto-Allowed</span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span>Teardown Action:</span>
                      <span className="text-amber-500 font-semibold">Reclaim & revoke NSG rules on expiration</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div className="pt-2 border-t border-border flex justify-end">
              <button
                type="button"
                onClick={() => setConnectResource(null)}
                className="ops-primary px-5 py-2 text-xs font-semibold"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
