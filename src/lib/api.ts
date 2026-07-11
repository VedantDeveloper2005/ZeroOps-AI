// ============================================
// ZeroOps AI — Centralized API Client
// All data fetched from FastAPI backend (per-user, database-backed)
// ============================================

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const res = await fetch(url, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail;
    const msg = typeof detail === "string" 
      ? detail 
      : (detail && typeof detail === "object" && "details" in detail && typeof detail.details === "string"
        ? detail.details 
        : (detail && typeof detail === "object" && "error" in detail && typeof detail.error === "string"
          ? detail.error
          : `Request failed: ${res.status}`));
    throw new ApiError(res.status, msg, detail);
  }

  // Handle 204 No Content
  if (res.status === 204) return {} as T;
  return res.json();
}

async function requestForm<T>(path: string, formData: FormData): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const res = await fetch(url, {
    method: "POST",
    credentials: "include",
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail;
    const msg = typeof detail === "string"
      ? detail
      : (detail && typeof detail === "object" && "details" in detail && typeof detail.details === "string"
        ? detail.details
        : (detail && typeof detail === "object" && "error" in detail && typeof detail.error === "string"
          ? detail.error
          : `Request failed: ${res.status}`));
    throw new ApiError(res.status, msg, detail);
  }

  return res.json();
}

export class ApiError extends Error {
  status: number;
  details?: unknown;
  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.details = details;
    this.name = "ApiError";
  }
}

export function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error && error.message) return error.message;
  if (
    typeof error === "object" &&
    error !== null &&
    "message" in error &&
    typeof (error as { message?: unknown }).message === "string"
  ) {
    return (error as { message: string }).message;
  }
  return fallback;
}

// ──────────────────────────────────────────────
// TYPES
// ──────────────────────────────────────────────

export interface Project {
  id: string;
  name: string;
  full_name: string;
  repo_url: string | null;
  framework: string;
  language: string;
  branch: string;
  region: string;
  status: string;
  last_deployed_at: string | null;
  created_at: string | null;
  deployment_count: number;
  latest_deployment_status: string | null;
}

export interface Deployment {
  id: string;
  project_id: string;
  project_name: string | null;
  status: "queued" | "building" | "deploying" | "running" | "failed" | "stopped" | "rolled_back";
  environment: "production" | "staging" | "development";
  branch: string;
  version: string | null;
  commit_sha: string | null;
  image: string | null;
  duration_seconds: number | null;
  duration: string | null;
  live_url: string | null;
  deployed_by: string;
  started_at: string | null;
  completed_at: string | null;
  infrastructure_metadata?: Record<string, unknown> | null;
}

export interface DeploymentLog {
  line_number: number;
  level: "INFO" | "WARN" | "ERROR" | "DEBUG";
  message: string;
  timestamp: string | null;
}

export interface DeploymentDetail extends Deployment {
  logs: DeploymentLog[];
}

export interface Notification {
  id: string;
  title: string;
  message: string;
  type: "info" | "success" | "warning" | "critical";
  category: string;
  read: boolean;
  action_url: string | null;
  created_at: string | null;
}

export interface AIAction {
  id: string;
  project_id: string | null;
  type: "scaling" | "security" | "deployment" | "optimization" | "healing" | "monitoring";
  severity: "info" | "warning" | "success" | "critical";
  message: string;
  recommendation: string | null;
  status: "pending" | "applied" | "dismissed";
  icon: string;
  created_at: string | null;
}

export interface AIAnalysis {
  id: string;
  project_id: string | null;
  framework: string | null;
  framework_version: string | null;
  language: string | null;
  risk_score: number;
  confidence: number;
  cpu_recommendation: string | null;
  memory_recommendation: string | null;
  storage_recommendation: string | null;
  port: string | null;
  dependencies: string[];
  vulnerabilities: string[];
  dockerfile: string | null;
  kubernetes_manifest: string | null;
  created_at: string | null;

  // Extra AI analysis fields
  runtime: string | null;
  package_manager: string | null;
  docker_support: boolean;
  monorepo_structure: string | null;
  database_dependencies: string[];
  deployment_strategy: string | null;
  build_commands: string | null;
  start_commands: string | null;
  environment_variables: string[];
  explanation?: string | null;
  
  // New blueprint fields
  application_type?: string | null;
  estimated_build_time?: string | null;
  production_readiness_score?: number | null;
  detected_services?: string[];
}

export interface DeploymentRecommendation {
  id: string;
  project_id: string | null;
  repository_full_name: string;
  recommended_target: string | null;
  azure_configuration: Record<string, unknown>;
  environment_variables: string[];
  scaling_recommendation: Record<string, unknown>;
  database_recommendation: Record<string, unknown>;
  estimated_deployment_time: string | null;
  created_at: string | null;
}

export interface FailureAnalysis {
  id: string;
  project_id: string;
  deployment_id: string;
  failure_summary: string;
  root_cause: string;
  severity: string;
  recommended_fix: string;
  step_by_step_resolution: string[];
  confidence?: number;
  impact?: string;
  created_at: string | null;
}

export interface DashboardStats {
  total_projects: number;
  total_deployments: number;
  active_deployments: number;
  failed_deployments: number;
  security_score: number;
  pending_ai_actions: number;
  unread_notifications: number;
  has_deployed: boolean;
}

export interface UserProfile {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  avatar_url: string | null;
  plan: string;
  provider: string;
  created_at: string | null;
  total_projects: number;
  total_deployments: number;
  active_deployments: number;
}

export interface UserSettings {
  predictive_scaling: boolean;
  auto_rollback: boolean;
  ai_threat_mitigation: boolean;
  auto_oom_restart: boolean;
  slack_notifications: boolean;
  email_alerts: boolean;
  theme: string;
}

export interface GitHubRepoItem {
  id: number;
  name: string;
  full_name: string;
  description: string | null;
  private: boolean;
  language: string | null;
  stargazers_count: number;
  default_branch: string;
  updated_at: string;
  html_url: string;
  owner_avatar_url: string | null;
}

export interface GitHubReposResponse {
  repos: GitHubRepoItem[];
  total_count: number;
  page: number;
  per_page: number;
  has_next: boolean;
}

export interface GitHubStatus {
  connected: boolean;
  username: string | null;
  avatar_url: string | null;
}

// Keep old interface as alias for backward compatibility
export type GitHubRepo = GitHubRepoItem;

export interface EnvVar {
  id: string;
  key: string;
  value: string;
  is_secret: boolean;
  created_at: string | null;
}

export interface TelemetryMetric {
  cpu: { time: string; value: number }[];
  memory: { time: string; value: number }[];
  uptime: string;
  error_rate: string;
  response_time: string;
  request_count: number;
}

export interface SecurityStatus {
  securityScore: number;
  firewallStatus: string;
  httpsStatus: string;
  secretsManaged: number;
  vulnerabilities: number;
  soc2Status: string;
  threatLevel: string;
  namespaceIsolated: boolean;
  rbacEnabled: boolean;
}

export interface CustomDomain {
  name: string;
  default: boolean;
  ssl: boolean;
  dns_verified: boolean;
  https_enabled: boolean;
  created_at: string;
}

export interface ProjectMember {
  email: string;
  role: string;
  name: string;
  joined_at: string;
}

export interface ProjectActivity {
  id: string;
  project_id: string | null;
  project_name?: string;
  action: string;
  details: string | null;
  created_at: string;
}

export interface HealthScore {
  score: number;
  status: string;
  breakdown: {
    performance: number;
    security: number;
    reliability: number;
    scalability: number;
    cost: number;
  };
  recommendations: string[];
}

export interface CostOptimization {
  current_cost: number;
  recommended_cost: number;
  savings: number;
  recommendations: {
    title: string;
    description: string;
    savings: number;
  }[];
}

export interface BillingOperation {
  id: string;
  operation_type: string;
  status: string;
  amount_cents: number;
  currency: string;
  description: string | null;
  project_id: string | null;
  deployment_id: string | null;
  provider?: string | null;
  provider_reference?: string | null;
  checkout_url?: string | null;
  created_at: string | null;
  paid_at: string | null;
  consumed_at: string | null;
}

export interface AzureConnection {
  connected: boolean;
  tenant_id?: string | null;
  subscription_id?: string | null;
  client_id?: string | null;
  region?: string | null;
  resource_group?: string | null;
  acr_login_server?: string | null;
  container_apps_environment?: string | null;
  namespace_prefix?: string | null;
}

export interface DeploymentTargetStatus {
  provider: "azure-container-apps";
  label: string;
  ready: boolean;
  missing: string[];
  region?: string | null;
  environment_name?: string | null;
  registry?: string | null;
}

export interface DeploymentTargetsStatus {
  any_ready: boolean;
  targets: DeploymentTargetStatus[];
}

export interface SystemHealth {
  status: string;
  service: string;
  environment: string;
  azureDeploymentWorker: boolean;
  openAIConfigured: boolean;
}

export interface HealthCheck {
  status: string;
  details: string;
}

export interface DeploymentHealth {
  status: string;
  total_deployments: number;
  active_deployments_running: number;
}

export interface ClusterResourceMetrics {
  available: boolean;
  message?: string;
  cpu?: number | null;
  memory?: number | null;
  podsHealthy?: number;
  podsTotal?: number;
  traffic?: number | null;
  errorRate?: number | null;
}

// ──────────────────────────────────────────────
// API CLIENT
// ──────────────────────────────────────────────

export const api = {
  // ── Projects ──
  getProjects: () => request<Project[]>("/api/projects"),

  createProject: (data: {
    name: string;
    full_name: string;
    repo_url?: string;
    framework?: string;
    language?: string;
    branch?: string;
    region?: string;
  }) => request<Project>("/api/projects", { method: "POST", body: JSON.stringify(data) }),

  uploadCode: (file: File) => {
    const formData = new FormData();
    formData.set("file", file);
    return requestForm<{ project: Project; analysis: Record<string, unknown> }>("/api/projects/upload", formData);
  },

  getProject: (id: string) => request<Project>(`/api/projects/${id}`),

  deleteProject: (id: string) => request<void>(`/api/projects/${id}`, { method: "DELETE" }),

  // ── Deployments ──
  getDeployments: (limit = 20) => request<Deployment[]>(`/api/deployments?limit=${limit}`),

  startDeployment: (data: {
    project_id: string;
    branch?: string;
    environment?: string;
    target_provider?: "auto" | "azure" | "azure-container-apps";
  }) => request<{ status: string; deployment_id: string; project_id: string }>(
    "/api/deployments/deploy",
    { method: "POST", body: JSON.stringify(data) }
  ),

  getDeployment: (id: string) => request<DeploymentDetail>(`/api/deployments/${id}`),

  // ── Notifications ──
  getNotifications: (category?: string, limit = 50) => {
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    params.set("limit", String(limit));
    return request<Notification[]>(`/api/notifications?${params}`);
  },

  markNotificationRead: (id: string) =>
    request<void>(`/api/notifications/${id}/read`, { method: "POST" }),

  markAllNotificationsRead: () =>
    request<void>("/api/notifications/read-all", { method: "POST" }),

  // ── AI Actions ──
  getAIActions: (opts?: { status?: string; type?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    if (opts?.type) params.set("type", opts.type);
    if (opts?.limit) params.set("limit", String(opts.limit));
    return request<AIAction[]>(`/api/ai/actions?${params}`);
  },

  applyAIAction: (id: string) =>
    request<void>(`/api/ai/actions/${id}/apply`, { method: "POST" }),

  dismissAIAction: (id: string) =>
    request<void>(`/api/ai/actions/${id}/dismiss`, { method: "POST" }),

  // ── AI Analysis ──
  getAIAnalysis: (projectId: string) =>
    request<AIAnalysis>(`/api/ai/analysis/${projectId}`),

  analyzeRepo: (repo: string, branch: string) =>
    request<Record<string, unknown>>("/api/ai/analyze", {
      method: "POST",
      body: JSON.stringify({ repo, branch }),
    }),

  getAIAnalysisHistory: (projectId: string) =>
    request<AIAnalysis[]>(`/api/projects/${projectId}/analyses`),

  sendChatRequest: (message: string, projectId?: string) =>
    request<{ reply: string }>("/api/ai/chat", {
      method: "POST",
      body: JSON.stringify({ message, project_id: projectId }),
    }),

  // ── Dashboard ──
  getDashboardStats: () => request<DashboardStats>("/api/dashboard/stats"),

  // ── User Profile ──
  getProfile: () => request<UserProfile>("/api/user/profile"),

  updateProfile: (data: { first_name?: string; last_name?: string; avatar_url?: string }) =>
    request<UserProfile>("/api/user/profile", { method: "PUT", body: JSON.stringify(data) }),

  // ── User Settings ──
  getSettings: () => request<UserSettings>("/api/user/settings"),

  updateSettings: (data: Partial<UserSettings>) =>
    request<UserSettings>("/api/user/settings", { method: "PUT", body: JSON.stringify(data) }),

  resetOnboarding: () =>
    request<{ status: string; message: string }>("/api/user/reset", { method: "POST" }),

  // ── Azure Deployment Target ──
  getAzureConnection: () => request<AzureConnection>("/api/azure/connection"),

  updateAzureConnection: (data: {
    tenant_id: string;
    subscription_id: string;
    client_id?: string;
    client_secret?: string;
    region?: string;
    resource_group?: string;
    acr_login_server?: string;
    container_apps_environment?: string;
    namespace_prefix?: string;
  }) =>
    request<AzureConnection>("/api/azure/connection", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // ── Google GKE Deployment Target ──
  getDeploymentTargets: () => request<DeploymentTargetsStatus>("/api/deployment-targets"),

  // ── GitHub OAuth ──
  getGitHubStatus: () => request<GitHubStatus>("/api/github/status"),

  getGitHubRepos: (opts?: {
    page?: number;
    per_page?: number;
    sort?: string;
    q?: string;
  }) => {
    const params = new URLSearchParams();
    if (opts?.page) params.set("page", String(opts.page));
    if (opts?.per_page) params.set("per_page", String(opts.per_page));
    if (opts?.sort) params.set("sort", opts.sort);
    if (opts?.q) params.set("q", opts.q);
    return request<GitHubReposResponse>(`/api/github/repos?${params}`);
  },

  getRepoBranches: (repo: string) =>
    request<{ branches: string[] }>(`/api/github/branches?repo=${encodeURIComponent(repo)}`),

  disconnectGitHub: () =>
    request<void>("/api/github/disconnect", { method: "POST" }),

  getRepoMetadata: (repo: string) =>
    request<{ branches: string[] }>(`/api/github/repo-metadata?repo=${encodeURIComponent(repo)}`),

  // ── Health & Diagnostics ──
  getHealth: () => request<{
    status: string;
    service: string;
    environment: string;
    azureDeploymentWorker: boolean;
    openAIConfigured: boolean;
  }>("/api/health"),

  getHealthDatabase: () => request<{
    status: string;
    details: string;
  }>("/api/health/database"),

  getHealthGithub: () => request<{
    status: string;
    details: string;
  }>("/api/health/github"),

  getHealthDeployments: () => request<{
    status: string;
    total_deployments: number;
    active_deployments_running: number;
  }>("/api/health/deployments"),

  // ── Monitoring ──
  getMetrics: (projectId?: string) => {
    const params = projectId ? `?project_id=${projectId}` : "";
    return request<ClusterResourceMetrics>(`/api/monitoring/metrics${params}`);
  },

  // ── Secrets ──
  addSecret: (projectId: string, key: string, value: string) =>
    request<void>("/api/secrets", {
      method: "POST",
      body: JSON.stringify({ projectId, key, value }),
    }),

  getSecrets: (projectId: string) =>
    request<{ key: string; value: string }[]>(`/api/secrets/${projectId}`),

  deleteSecret: (projectId: string, key: string) =>
    request<void>(`/api/secrets/${projectId}/${key}`, { method: "DELETE" }),

  // ── Security ──
  getSecurityStatus: (projectId: string) =>
    request<SecurityStatus>(`/api/security/status/${projectId}`),

  // ── Autoscaling ──
  getAutoscalingStatus: (projectId: string) =>
    request<Record<string, unknown>>(`/api/autoscaling/${projectId}`),

  configureAutoscaling: (data: {
    projectId: string;
    minReplicas: number;
    maxReplicas: number;
    cpuTarget: number;
  }) =>
    request<void>("/api/autoscaling/configure", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // ── API Key ──
  getApiKey: () => request<{ apiKey: string }>("/api/settings/api-key"),
  regenerateApiKey: () =>
    request<{ apiKey: string }>("/api/settings/api-key/regenerate", {
      method: "POST",
    }),

  // ── Project Metrics & Env Vars ──
  getProjectMetrics: (projectId: string) =>
    request<TelemetryMetric>(`/api/projects/${projectId}/metrics`),

  getEnvVars: (projectId: string) =>
    request<EnvVar[]>(`/api/projects/${projectId}/variables`),

  addEnvVar: (projectId: string, data: { key: string; value: string; is_secret: boolean }) =>
    request<EnvVar>(`/api/projects/${projectId}/variables`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  deleteEnvVar: (projectId: string, varId: string) =>
    request<void>(`/api/projects/${projectId}/variables/${varId}`, {
      method: "DELETE",
    }),

  // ── AI Recommendations & Failures ──
  getProjectRecommendations: (projectId: string) =>
    request<DeploymentRecommendation>(`/api/projects/${projectId}/recommendations`),

  getDeploymentFailureAnalysis: (deploymentId: string) =>
    request<FailureAnalysis>(`/api/deployments/${deploymentId}/failure-analysis`),

  // ── Collaboration & Optimization Endpoints ──
  getHealthScore: (projectId: string) =>
    request<HealthScore>(`/api/projects/${projectId}/health-score`),

  getCostOptimization: (projectId: string) =>
    request<CostOptimization>(`/api/projects/${projectId}/cost-optimization`),

  createBillingOperation: (data: {
    operation_type: string;
    project_id?: string;
    deployment_id?: string;
    description?: string;
  }) =>
    request<BillingOperation>("/api/billing/operations", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getBillingOperations: () => request<BillingOperation[]>("/api/billing/operations"),

  createBillingCheckout: (operationId: string) =>
    request<BillingOperation>(`/api/billing/operations/${operationId}/checkout`, {
      method: "POST",
    }),

  getProjectDomains: (projectId: string) =>
    request<CustomDomain[]>(`/api/projects/${projectId}/domains`),

  connectDomain: (projectId: string, name: string) =>
    request<CustomDomain[]>(`/api/projects/${projectId}/domains`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  verifyDomain: (projectId: string, name: string) =>
    request<CustomDomain[]>(`/api/projects/${projectId}/domains/${name}/verify`, {
      method: "POST",
    }),

  renewSSL: (projectId: string, name: string) =>
    request<CustomDomain[]>(`/api/projects/${projectId}/domains/${name}/renew-ssl`, {
      method: "POST",
    }),

  removeDomain: (projectId: string, name: string) =>
    request<CustomDomain[]>(`/api/projects/${projectId}/domains/${name}`, {
      method: "DELETE",
    }),

  getProjectMembers: (projectId: string) =>
    request<ProjectMember[]>(`/api/projects/${projectId}/members`),

  addMember: (projectId: string, email: string, role: string) =>
    request<ProjectMember[]>(`/api/projects/${projectId}/members`, {
      method: "POST",
      body: JSON.stringify({ email, role }),
    }),

  removeMember: (projectId: string, email: string) =>
    request<ProjectMember[]>(`/api/projects/${projectId}/members/${email}`, {
      method: "DELETE",
    }),

  getProjectActivity: (projectId: string) =>
    request<ProjectActivity[]>(`/api/projects/${projectId}/activity`),

  getGlobalActivity: () =>
    request<ProjectActivity[]>("/api/activity"),

  fixDeploymentAutomatically: (deployId: string) =>
    request<{ status: string; message: string; deployment_id: string; project_id: string }>(
      `/api/deployments/${deployId}/fix-auto`,
      { method: "POST" }
    ),

  selfHeal: (projectId: string, action: string) =>
    request<{ status: string; message: string; deployment_id?: string }>(
      `/api/projects/${projectId}/self-heal`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      }
    ),
};

