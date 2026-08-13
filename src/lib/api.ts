// ============================================
// ZeroOps AI — Centralized API Client
// All data fetched from FastAPI backend (per-user, database-backed)
// ============================================

const CSRF_HEADER = "X-CSRF-Token";
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

let csrfToken: string | null = null;
let csrfBootstrap: Promise<void> | null = null;

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit,
  timeoutMs: number,
) {
  const controller = new AbortController();
  const upstreamSignal = init.signal;
  const forwardAbort = () => controller.abort();
  if (upstreamSignal?.aborted) controller.abort();
  else upstreamSignal?.addEventListener("abort", forwardAbort, { once: true });
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    globalThis.clearTimeout(timeout);
    upstreamSignal?.removeEventListener("abort", forwardAbort);
  }
}

function rememberCsrfToken(response: Response) {
  const token = response.headers.get(CSRF_HEADER);
  if (token) csrfToken = token;
}

async function ensureCsrfToken() {
  if (csrfToken || typeof window === "undefined") return;
  if (!csrfBootstrap) {
    csrfBootstrap = fetchWithTimeout(
      "/api/health",
      { credentials: "include" },
      10_000,
    )
      .then(rememberCsrfToken)
      .catch(() => undefined)
      .finally(() => {
        csrfBootstrap = null;
      });
  }
  await csrfBootstrap;
}

function requestHeaders(options: RequestInit | undefined, includeJsonContentType: boolean) {
  const headers = new Headers(options?.headers);
  if (includeJsonContentType && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const method = (options?.method || "GET").toUpperCase();
  if (UNSAFE_METHODS.has(method) && csrfToken && !headers.has(CSRF_HEADER)) {
    headers.set(CSRF_HEADER, csrfToken);
  }
  return headers;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const method = (options?.method || "GET").toUpperCase();
  if (UNSAFE_METHODS.has(method)) await ensureCsrfToken();
  const res = await fetchWithTimeout(
    path,
    {
      ...options,
      credentials: "include",
      headers: requestHeaders(options, true),
    },
    30_000,
  );
  rememberCsrfToken(res);

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
  await ensureCsrfToken();
  const res = await fetchWithTimeout(
    path,
    {
      method: "POST",
      credentials: "include",
      headers: requestHeaders({ method: "POST" }, false),
      body: formData,
    },
    120_000,
  );
  rememberCsrfToken(res);

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

export function isCapabilityUnavailable(error: unknown) {
  return (
    error instanceof ApiError &&
    [405, 501, 503].includes(error.status)
  );
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
  mfa_method?: string;
  email_verified?: boolean;
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

export interface MFAStatus {
  enabled: boolean;
  method?: string;
  recovery_codes_remaining: number;
}

export interface MFASetup {
  manual_key: string;
  otpauth_uri: string;
  qr_code_data_uri: string;
  expires_at: string;
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

export type PipelineStageStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "skipped"
  | "blocked"
  | "unavailable"
  | "cancelled";

export type PipelineRunStatus =
  | PipelineStageStatus
  | "waiting_for_approval"
  | "completed";

export type PipelineApprovalStatus =
  | "not_required"
  | "required"
  | "pending"
  | "approved"
  | "approved_consumed"
  | "rejected";

export type PipelineTrigger =
  | "manual"
  | "github_push"
  | "push"
  | "retry"
  | "api"
  | "remediation";

export type DeploymentProvider = "azure-app-service" | "azure-aks";

export interface PipelineEvidence {
  id?: string;
  label: string;
  value: string;
  kind?: "text" | "commit" | "artifact" | "policy" | "log" | "url";
  url?: string | null;
  sensitive?: boolean;
}

export interface PipelineStageAttempt {
  id: string;
  pipeline_run_id?: string;
  stage_key: string;
  name: string;
  description?: string | null;
  order: number;
  attempt: number;
  status: PipelineStageStatus;
  required: boolean;
  tool?: string | null;
  reason?: string | null;
  summary?: string | null;
  evidence?: PipelineEvidence[];
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds?: number | null;
  duration_label?: string | null;
  logs_available?: boolean;
  log_count?: number;
  ai_used?: boolean;
  approval_required?: boolean;
}

export type ChangeClassification =
  | "NO_RELEVANT_CHANGE"
  | "APPLICATION_CODE_CHANGE"
  | "DEPENDENCY_CHANGE"
  | "DEPLOYMENT_CONFIG_CHANGE"
  | "INFRASTRUCTURE_CHANGE"
  | "KUBERNETES_CHANGE"
  | "SECURITY_RELEVANT_CHANGE"
  | "MAJOR_ARCHITECTURE_CHANGE";

export interface ChangeAnalysis {
  id: string;
  project_id: string;
  deployment_id?: string | null;
  previous_commit_sha?: string | null;
  current_commit_sha: string;
  classifications: ChangeClassification[];
  changed_paths?: string[];
  architecture_analysis_required: boolean;
  architecture_analysis_reason: string;
  ai_used: boolean;
  decision_source: string;
  created_at: string | null;
}

export type PipelineDeploymentMode =
  | "validate_only"
  | "deploy_after_checks"
  | "require_approval";

export interface PipelineConfiguration {
  // API presentation DTO. The backend adapter maps these names to the
  // versioned ProjectPipelineConfiguration persistence fields.
  project_id: string;
  automatic_deployment: boolean;
  branch: string;
  deployment_mode: PipelineDeploymentMode;
  run_tests: boolean;
  sast_enabled: boolean;
  dependency_scan_enabled: boolean;
  secret_scan_enabled: boolean;
  container_scan_enabled: boolean;
  iac_scan_enabled: boolean;
  production_approval_required: boolean;
  ai_failure_diagnosis_enabled: boolean;
  auto_retry_transient_failures: boolean;
  auto_rollback_enabled: boolean;
  /** A signing secret exists. This does not verify GitHub webhook installation or delivery. */
  github_webhook_secret_configured: boolean;
  updated_at: string | null;
}

export type PipelineConfigurationUpdate = Omit<
  PipelineConfiguration,
  "project_id" | "github_webhook_secret_configured" | "updated_at"
>;

type PipelineConfigurationWire = Omit<
  PipelineConfiguration,
  "github_webhook_secret_configured"
> & {
  github_webhook_secret_configured?: boolean;
  /** Backward-compatible server field; it only represents stored secret state. */
  github_webhook_configured?: boolean;
};

function normalizePipelineConfiguration(
  configuration: PipelineConfigurationWire,
): PipelineConfiguration {
  const {
    github_webhook_configured,
    github_webhook_secret_configured,
    ...rest
  } = configuration;

  return {
    ...rest,
    github_webhook_secret_configured:
      github_webhook_secret_configured ?? github_webhook_configured ?? false,
  };
}

export interface GitHubWebhookSecretResponse {
  webhook_url: string;
  secret: string;
  warning: string;
}

export type SecuritySeverity = "critical" | "high" | "medium" | "low" | "info";

export type SecurityScanCategory =
  | "sast"
  | "dependency"
  | "secret"
  | "container"
  | "iac"
  | "kubernetes"
  | "sbom";

export interface SecurityFinding {
  id: string;
  category: string;
  severity: SecuritySeverity;
  title: string;
  description?: string | null;
  scanner: string;
  rule_id?: string | null;
  file_path?: string | null;
  line_number?: number | null;
  remediation?: string | null;
  blocking: boolean;
  redacted: boolean;
}

export interface SecurityToolResult {
  category: SecurityScanCategory;
  tool: string;
  status: PipelineStageStatus;
  reason?: string | null;
  blocking_findings: number;
  finding_count: number;
  completed_at?: string | null;
}

export interface SecurityScan {
  id: string;
  project_id: string;
  deployment_id?: string | null;
  commit_sha?: string | null;
  status: PipelineStageStatus;
  policy_result: "pending" | "passed" | "warning" | "blocked" | "unavailable";
  blocking_findings: number;
  finding_counts: Partial<Record<SecuritySeverity, number>>;
  tools: SecurityToolResult[];
  findings: SecurityFinding[];
  started_at?: string | null;
  completed_at?: string | null;
}

export interface ProjectSecurityOverview {
  project_id: string;
  latest_scan: SecurityScan | null;
  key_vault_status: "configured" | "not_configured" | "unavailable";
  rbac_status: "configured" | "not_configured" | "unavailable";
}

export interface AIInvestigation {
  id: string;
  project_id: string;
  deployment_id?: string | null;
  incident_id?: string | null;
  failed_stage_attempt_id?: string | null;
  status: PipelineStageStatus;
  failure_summary?: string | null;
  probable_root_cause?: string | null;
  confidence?: number | null;
  evidence?: PipelineEvidence[];
  recommended_fix?: string | null;
  safe_automatic_action_available: boolean;
  requires_user_action: boolean;
  resolution_steps?: string[];
  sanitized_context: boolean;
  unavailable_reason?: string | null;
  created_at: string | null;
  completed_at?: string | null;
}

export type IncidentSeverity = "critical" | "high" | "medium" | "low" | "info";
export type IncidentStatus =
  | "open"
  | "investigating"
  | "awaiting_approval"
  | "remediating"
  | "mitigated"
  | "resolved"
  | "dismissed";

export interface IncidentEvidence {
  id?: string;
  source: string;
  summary: string;
  recorded_at?: string | null;
}

export interface Incident {
  id: string;
  project_id: string;
  deployment_id?: string | null;
  deployment_revision?: string | null;
  title: string;
  summary: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  rule: string;
  detected_at: string;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
  evidence: IncidentEvidence[];
  investigation?: AIInvestigation | null;
  remediation_proposals?: RemediationProposal[];
}

export type RemediationRisk = "low" | "medium" | "high";
export type RemediationStatus =
  | "proposed"
  | "pending_approval"
  | "approved"
  | "rejected"
  | "expired"
  | "execution_queued"
  | "executing"
  | "executed"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "unavailable";

export interface RemediationProposal {
  id: string;
  incident_id?: string | null;
  deployment_id?: string | null;
  title: string;
  description: string;
  action_type: string;
  risk: RemediationRisk;
  status: RemediationStatus;
  requires_approval: boolean;
  safe_automatic_action: boolean;
  evidence?: PipelineEvidence[];
  created_at: string | null;
}

export interface RemediationExecution {
  id: string;
  proposal_id: string;
  status:
    | "queued"
    | "running"
    | "succeeded"
    | "failed"
    | "unavailable"
    | "cancelled";
  requested_by: string;
  verification_status?: PipelineStageStatus;
  attempt?: number;
  executor_kind?: "deterministic" | "operator" | "automation";
  executor_name?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  verification_summary?: string | null;
  error?: string | null;
}

export interface PipelineRun {
  id: string;
  project_id: string;
  deployment_id: string | null;
  status: PipelineRunStatus;
  trigger: PipelineTrigger;
  branch: string;
  commit_sha?: string | null;
  target_provider?: DeploymentProvider | null;
  progress_percent: number;
  reason?: string | null;
  failure_code?: string | null;
  approval_required: boolean;
  approval_status: PipelineApprovalStatus;
  approved_deployment_id?: string | null;
  approved_pipeline_run_id?: string | null;
  stages: PipelineStageAttempt[];
  change_analysis?: ChangeAnalysis | null;
  security_scan?: SecurityScan | null;
  investigation?: AIInvestigation | null;
  created_at: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface PipelineApprovalDecisionResponse {
  status: "approved" | "rejected";
  approval_status: "approved_consumed" | "rejected";
  idempotent?: boolean;
  validation_pipeline_run_id: string;
  deployment_id: string;
  pipeline_run_id?: string;
}

export type MonitoringWindow = "live" | "1h" | "6h" | "24h";

export interface MonitoringSample {
  recorded_at: string;
  cpu_percent?: number | null;
  memory_percent?: number | null;
  request_rate?: number | null;
  response_latency_ms?: number | null;
  http_error_rate_percent?: number | null;
  availability_percent?: number | null;
  pod_restarts?: number | null;
  pods_ready?: number | null;
  replica_count?: number | null;
  failed_pods?: number | null;
}

export interface ProjectMonitoring {
  project_id: string;
  window: MonitoringWindow;
  available_windows?: MonitoringWindow[];
  availability: "available" | "no_telemetry" | "unavailable";
  source?: string | null;
  target_provider?: DeploymentProvider | null;
  deployment_revision?: string | null;
  deployment_health?: string | null;
  latest_incidents?: Incident[];
  samples: MonitoringSample[];
  message?: string | null;
}

export interface SecurityStatus {
  securityScore: number | null;
  firewallStatus: string;
  httpsStatus: string;
  secretsManaged: number;
  vulnerabilities: number;
  soc2Status: string;
  threatLevel: string;
  namespaceIsolated: boolean;
  rbacEnabled: boolean;
}

export interface ProjectActivity {
  id: string;
  project_id: string | null;
  project_name?: string;
  action: string;
  details: string | null;
  created_at: string;
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
  app_service_plan?: string | null;
  aks_cluster_name?: string | null;
  namespace_prefix?: string | null;
  deployment_target_verified_at?: string | null;
}

export interface DeploymentTargetStatus {
  provider: DeploymentProvider;
  label: string;
  ready: boolean;
  missing: string[];
  region?: string | null;
  plan_name?: string | null;
  registry?: string | null;
  cluster_name?: string | null;
}

export interface AKSDeploymentTargetStatus extends DeploymentTargetStatus {
  provider: "azure-aks";
  namespace?: string | null;
  workload?: string | null;
  image_digest?: string | null;
  deployment_revision?: string | null;
  service_endpoint?: string | null;
  rollout_status?: string | null;
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

export interface RuntimeResourceMetrics {
  available: boolean;
  message?: string;
  cpu?: number | null;
  memory?: number | null;
  traffic?: number | null;
  errorRate?: number | null;
}

export interface InfrastructurePlanComponent {
  id: string;
  category: string;
  service: string;
  tier: string | null;
  reason: string;
  recommended: boolean;
  deployable: boolean;
  available_services: string[];
}

export interface InfrastructureCostBreakdownItem {
  component: string;
  cost_monthly: number;
  tier: string;
}

export interface InfrastructurePlan {
  id: string;
  project_id: string;
  provider: string;
  region: string;
  status: "draft" | "approved" | "provisioning" | "deployed";
  revision: number;
  plan: {
    cloud: string;
    region_label: string;
    application_evidence: {
      framework?: string | null;
      runtime?: string | null;
      package_manager?: string | null;
      docker_support?: boolean;
      database_dependencies?: string[];
      environment_variable_names?: string[];
    };
    components: InfrastructurePlanComponent[];
    cost: { status: string; monthly_estimate: number | null; message: string };
    deployment_time: { status: string; estimate: string | null; message: string };
    assessment: {
      security: { status: string; value: number | null };
      performance: { status: string; value: number | null };
      reliability: { status: string; value: number | null };
      source_findings: string[];
      unresolved_questions: string[];
      readiness_message: string;
    };
    deployment: { approval_required: boolean; engine: string; summary: string };
  };
  cost_estimate?: {
    status: string;
    monthly_estimate: number | null;
    breakdown?: InfrastructureCostBreakdownItem[];
  };
  security_score?: number | null;
  performance_score?: number | null;
  reliability_score?: number | null;
  estimated_deploy_time?: string | null;
  ai_explanations?: Record<string, string>;
  approval_note: string | null;
  approved_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface InfrastructurePlanUpdate {
  region?: string;
  component_id?: string;
  service?: string;
  tier?: string;
}

export interface KnowledgeGraphNode {
  id: string;
  type: string;
  label: string;
  properties: Record<string, unknown>;
}

export interface KnowledgeGraph {
  project_id: string;
  plan_revision: number | null;
  graph: {
    version: number;
    model: string;
    plan_revision: number | null;
    nodes: KnowledgeGraphNode[];
    edges: { source: string; target: string; relation: string }[];
  };
  generated_at: string | null;
}

export interface DigitalTwinSimulation {
  id: string;
  project_id: string;
  plan_revision: number | null;
  model: string;
  status: "ready" | "requires_review" | "blocked";
  risk_score: number;
  risk_level: "low" | "moderate" | "high" | "critical";
  summary: string;
  snapshot: {
    project?: string;
    plan_revision?: number | null;
    region?: string | null;
    application_service?: string | null;
    component_count?: number;
    target_ready?: boolean;
    target_labels?: string[];
  };
  checks: { id: string; label: string; status: "passed" | "warning" | "blocked"; detail: string; risk_weight: number }[];
  proposed_changes: string[];
  created_at: string | null;
}

export interface DecisionAccuracy {
  available: boolean;
  outcome_accuracy_percent: number | null;
  evaluated_deployments: number;
  successful_deployments: number;
  failed_deployments: number;
  pending_deployments: number;
  methodology: string;
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

  getInfrastructurePlan: (projectId: string) =>
    request<InfrastructurePlan>(`/api/projects/${projectId}/infrastructure-plan`),

  generateInfrastructurePlan: (projectId: string) =>
    request<InfrastructurePlan>(`/api/projects/${projectId}/infrastructure-plan/generate`, { method: "POST" }),

  updateInfrastructurePlan: (projectId: string, data: InfrastructurePlanUpdate) =>
    request<InfrastructurePlan>(`/api/projects/${projectId}/infrastructure-plan`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  approveInfrastructurePlan: (projectId: string, note?: string) =>
    request<InfrastructurePlan>(`/api/projects/${projectId}/infrastructure-plan/approve`, {
      method: "POST",
      body: JSON.stringify({ note }),
    }),

  getKnowledgeGraph: (projectId: string) =>
    request<KnowledgeGraph>(`/api/projects/${projectId}/knowledge-graph`),

  simulateDigitalTwin: (projectId: string) =>
    request<DigitalTwinSimulation>(`/api/projects/${projectId}/digital-twin/simulate`, { method: "POST" }),

  getLatestDigitalTwin: (projectId: string) =>
    request<DigitalTwinSimulation>(`/api/projects/${projectId}/digital-twin/latest`),

  getDecisionAccuracy: (projectId: string) =>
    request<DecisionAccuracy>(`/api/projects/${projectId}/decision-accuracy`),

  deleteProject: (id: string) => request<void>(`/api/projects/${id}`, { method: "DELETE" }),

  // ── Deployments ──
  getDeployments: (limit = 20) => request<Deployment[]>(`/api/deployments?limit=${limit}`),

  startDeployment: (data: {
    project_id: string;
    branch?: string;
    environment?: string;
    target_provider?: "auto" | "azure" | DeploymentProvider;
  }) => request<{ status: string; deployment_id: string; project_id: string }>(
    "/api/deployments/deploy",
    { method: "POST", body: JSON.stringify(data) }
  ),

  getDeployment: (id: string) => request<DeploymentDetail>(`/api/deployments/${id}`),

  getDeploymentPipeline: (id: string) =>
    request<PipelineRun>(`/api/deployments/${id}/pipeline`),

  approvePipelineRun: (id: string) =>
    request<PipelineApprovalDecisionResponse>(`/api/pipeline-runs/${id}/approve`, {
      method: "POST",
    }),

  rejectPipelineRun: (id: string) =>
    request<PipelineApprovalDecisionResponse>(`/api/pipeline-runs/${id}/reject`, {
      method: "POST",
    }),

  getProjectChangeAnalysis: (projectId: string) =>
    request<ChangeAnalysis[]>(`/api/projects/${projectId}/change-analysis`),

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
    request<{ reply: string; plan_updated?: boolean; infrastructure_plan?: InfrastructurePlan | null }>("/api/ai/chat", {
      method: "POST",
      body: JSON.stringify({ message, project_id: projectId }),
    }),

  analyzeRepository: (projectId: string) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/analyze`, { method: "POST" }),

  getProjectAnalysis: (projectId: string) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/analysis`),

  explainComponent: (projectId: string, componentId: string) =>
    request<{ explanation: string }>(`/api/projects/${projectId}/infrastructure-spec/explain/${componentId}`, {
      method: "POST"
    }),

  createDeploymentJob: (projectId: string, data: Record<string, unknown>) =>
    request<{ status: string; deployment_id: string; project_id: string }>(`/api/projects/${projectId}/deploy`, {
      method: "POST",
      body: JSON.stringify(data)
    }),

  getDeploymentJobStatus: (jobId: string) =>
    request<Record<string, unknown>>(`/api/deployment-jobs/${jobId}/status`),

  architectChat: (message: string, projectId: string) =>
    request<{ reply: string; plan_updated: boolean; plan: InfrastructurePlan | null }>("/api/ai/architect-chat", {
      method: "POST",
      body: JSON.stringify({ message, project_id: projectId })
    }),

  // ── Dashboard ──
  getDashboardStats: () => request<DashboardStats>("/api/dashboard/stats"),

  // ── User Profile ──
  getProfile: () => request<UserProfile>("/api/user/profile"),

  updateProfile: (data: { first_name?: string; last_name?: string; avatar_url?: string }) =>
    request<UserProfile>("/api/user/profile", { method: "PUT", body: JSON.stringify(data) }),

  // â”€â”€ Account security / MFA â”€â”€
  getMfaStatus: () => request<MFAStatus>("/api/auth/mfa/status"),
  startMfaSetup: () => request<MFASetup>("/api/auth/mfa/setup", { method: "POST" }),
  confirmMfaSetup: (code: string) =>
    request<{ recovery_codes: string[] }>("/api/auth/mfa/setup/confirm", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  disableMfa: (code: string) =>
    request<{ status: string; message: string }>("/api/auth/mfa/disable", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),

  verifyEmail: (email: string, token: string) =>
    request<{ status: string; message: string }>("/api/auth/verify-email", {
      method: "POST",
      body: JSON.stringify({ email, token }),
    }),

  resendVerification: (email: string) =>
    request<{ status: string; message: string }>("/api/auth/resend-verification", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  updateMfaMethod: (method: string) =>
    request<{ status: string; message: string }>("/api/auth/mfa/method", {
      method: "POST",
      body: JSON.stringify({ method }),
    }),

  setupEmailMfa: () =>
    request<{ recovery_codes: string[] }>("/api/auth/mfa/setup/email", {
      method: "POST",
    }),

  resendMfaOtp: () =>
    request<{ status: string; message: string }>("/api/auth/mfa/resend-otp", {
      method: "POST",
    }),

  // ── User Settings ──
  getSettings: () => request<UserSettings>("/api/user/settings"),

  updateSettings: (data: Partial<UserSettings>) =>
    request<UserSettings>("/api/user/settings", { method: "PUT", body: JSON.stringify(data) }),

  getPipelineConfiguration: async (projectId: string) =>
    normalizePipelineConfiguration(
      await request<PipelineConfigurationWire>(
        `/api/projects/${projectId}/pipeline-config`,
      ),
    ),

  updatePipelineConfiguration: async (
    projectId: string,
    data: PipelineConfigurationUpdate,
  ) =>
    normalizePipelineConfiguration(
      await request<PipelineConfigurationWire>(
        `/api/projects/${projectId}/pipeline-config`,
        {
          method: "PUT",
          body: JSON.stringify(data),
        },
      ),
    ),

  regenerateGitHubWebhookSecret: (projectId: string) =>
    request<GitHubWebhookSecretResponse>(
      `/api/projects/${projectId}/github-webhook-secret/regenerate`,
      { method: "POST" },
    ),

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
    app_service_plan?: string;
    aks_cluster_name?: string;
    namespace_prefix?: string;
  }) =>
    request<AzureConnection>("/api/azure/connection", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // ── Verified deployment targets ──
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
    return request<RuntimeResourceMetrics>(`/api/monitoring/metrics${params}`);
  },

  getProjectMonitoring: (projectId: string, window: MonitoringWindow = "live") =>
    request<ProjectMonitoring>(
      `/api/projects/${projectId}/monitoring?window=${encodeURIComponent(window)}`,
    ),

  // ── Security ──
  getSecurityStatus: (projectId: string) =>
    request<SecurityStatus>(`/api/security/status/${projectId}`),

  getProjectSecurityScans: (projectId: string) =>
    request<SecurityScan[]>(`/api/projects/${projectId}/security-scans`),

  // â”€â”€ Incidents & controlled remediation â”€â”€
  getProjectIncidents: (projectId: string) =>
    request<Incident[]>(`/api/projects/${projectId}/incidents`),

  getIncident: (incidentId: string) =>
    request<Incident>(`/api/incidents/${incidentId}`),

  acknowledgeIncident: (incidentId: string) =>
    request<Incident>(`/api/incidents/${incidentId}/acknowledge`, { method: "POST" }),

  dismissIncident: (incidentId: string) =>
    request<Incident>(`/api/incidents/${incidentId}/dismiss`, { method: "POST" }),

  requestIncidentInvestigation: (incidentId: string) =>
    request<AIInvestigation>(`/api/incidents/${incidentId}/investigate`, { method: "POST" }),

  approveRemediationProposal: (proposalId: string) =>
    request<RemediationProposal>(`/api/remediation-proposals/${proposalId}/approve`, {
      method: "POST",
    }),

  rejectRemediationProposal: (proposalId: string) =>
    request<RemediationProposal>(`/api/remediation-proposals/${proposalId}/reject`, {
      method: "POST",
    }),

  executeRemediationProposal: (proposalId: string) =>
    request<RemediationExecution>(`/api/remediation-proposals/${proposalId}/execute`, {
      method: "POST",
    }),

  // ── Autoscaling ──
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

  getProjectActivity: (projectId: string) =>
    request<ProjectActivity[]>(`/api/projects/${projectId}/activity`),

  getGlobalActivity: () =>
    request<ProjectActivity[]>("/api/activity"),

};

