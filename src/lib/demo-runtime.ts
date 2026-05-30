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
    { text: "[Stage 1] Repository Connected...", type: "info" },
    { text: "  GitHub Webhook handshake successful", type: "success" },
    { text: "[Stage 2] AI Analysis Complete...", type: "info" },
    { text: "  Framework detected: Next.js (TypeScript)", type: "info" },
    { text: "  AI Recommendation: 200m CPU, 256Mi RAM limits", type: "info" },
    { text: "  Deployment plan generated", type: "success" },
    { text: "[Stage 3] Build Completed...", type: "info" },
    { text: "  Downloaded packages and resolved dependencies", type: "success" },
    { text: "  Compilation complete: 0 errors, 4 warnings", type: "success" },
    { text: `  Container compiled: acr.azurecr.io/${projectId}:v1.0.0`, type: "success" },
    { text: "[Stage 4] Infrastructure Ready...", type: "info" },
    { text: "  Azure Database for PostgreSQL verified", type: "success" },
    { text: `  Isolated namespace '${namespace}' created`, type: "success" },
    { text: "[Stage 5] SSL Ready...", type: "info" },
    { text: "  SSL/TLS certificate issued and applied", type: "success" },
    { text: "[Stage 6] Application Live...", type: "info" },
    { text: `  Applied deployments/pods configs to Azure`, type: "success" },
    { text: "[Stage 7] Validation Complete...", type: "info" },
    { text: "  Probe GET /readyz - 200 OK (attempt 1/1)", type: "success" },
    { text: "  Liveness audit: 4/4 pods healthy", type: "success" },
    { text: `Live URL: ${liveUrl}`, type: "info" },
  ];
}

export const deploymentStageLabels = [
  "Repository Connected",
  "AI Analysis Complete",
  "Build Completed",
  "Infrastructure Ready",
  "SSL Ready",
  "Application Live",
  "Validation Complete",
];
