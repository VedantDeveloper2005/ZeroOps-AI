// ============================================
// ZeroOps AI — Runtime Utilities
// Utility functions for project naming, URL generation, and deployment simulation.
// No mock/fake data — all data comes from the backend API.
// ============================================

export const DEFAULT_PROJECT_ID = "web-app";
export const DEFAULT_NAMESPACE = `zeroops-${DEFAULT_PROJECT_ID}`;
export const DEFAULT_HOST = `${DEFAULT_PROJECT_ID}.zeroops.dev`;
export const DEFAULT_LIVE_URL = `https://${DEFAULT_HOST}`;

export function normalizeProjectId(repo: string) {
  const basename = repo.split("/").pop() || repo || DEFAULT_PROJECT_ID;
  return basename
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || DEFAULT_PROJECT_ID;
}

export function namespaceForProject(projectId: string) {
  return `zeroops-${normalizeProjectId(projectId)}`;
}

export function hostForProject(projectId: string) {
  return `${normalizeProjectId(projectId)}.zeroops.dev`;
}

export function liveUrlForProject(projectId: string) {
  return `https://${hostForProject(projectId)}`;
}

export interface TerminalLine {
  text: string;
  type: "command" | "info" | "success" | "warning" | "error" | "blank";
}

export function createSimulatedDeploymentLines(repo = "acme/web-app"): TerminalLine[] {
  const projectId = normalizeProjectId(repo);
  const namespace = namespaceForProject(projectId);
  const liveUrl = liveUrlForProject(projectId);

  return [
    { text: `$ zeroops deploy --repo ${repo} --env production`, type: "command" },
    { text: "", type: "blank" },
    { text: "ZeroOps AI deployment engine online", type: "info" },
    { text: `> Project identity resolved: ${projectId}`, type: "info" },
    { text: `> Namespace target: ${namespace}`, type: "info" },
    { text: "", type: "blank" },
    { text: "[Stage 1] Connecting Repository...", type: "info" },
    { text: "  GitHub Webhook handshake successful", type: "success" },
    { text: "[Stage 2] Cloning Source Code...", type: "info" },
    { text: "  Source code fetch complete: 12.4 MB", type: "success" },
    { text: "[Stage 3] AI Code Analysis...", type: "info" },
    { text: "  Framework detected: Next.js 16.2.6 (TypeScript)", type: "info" },
    { text: "  AI Recommendation: 200m CPU, 256Mi RAM limits", type: "info" },
    { text: "  Deployment plan generated", type: "success" },
    { text: "[Stage 4] Installing Dependencies...", type: "info" },
    { text: "  Downloaded 418 packages in 12s", type: "success" },
    { text: "[Stage 5] Building Application...", type: "info" },
    { text: "  Compilation complete: 0 errors, 4 warnings", type: "success" },
    { text: `  Container compiled successfully: acr.azurecr.io/${projectId}:v1.0.0`, type: "success" },
    { text: "[Stage 6] Generating Infrastructure...", type: "info" },
    { text: "  Generated: Deployment, Service, HPA, and Ingress manifests", type: "success" },
    { text: "[Stage 7] Provisioning Cloud Resources...", type: "info" },
    { text: "  Azure Database for PostgreSQL verified", type: "success" },
    { text: `  Isolated namespace '${namespace}' created`, type: "success" },
    { text: "[Stage 8] Deploying Containers...", type: "info" },
    { text: `  Applied deployments/pods configs to AKS`, type: "success" },
    { text: "[Stage 9] Health Check Verification...", type: "info" },
    { text: "  Probe GET /readyz - 200 OK (attempt 1/1)", type: "success" },
    { text: "  Liveness audit: 4/4 pods healthy", type: "success" },
    { text: "[Stage 10] Deployment Successful", type: "success" },
    { text: `Live URL: ${liveUrl}`, type: "info" },
  ];
}

export const deploymentStageLabels = [
  "Connecting Repository",
  "Cloning Source Code",
  "AI Code Analysis",
  "Installing Dependencies",
  "Building Application",
  "Generating Infrastructure",
  "Provisioning Cloud Resources",
  "Deploying Containers",
  "Health Check Verification",
  "Deployment Successful",
];
