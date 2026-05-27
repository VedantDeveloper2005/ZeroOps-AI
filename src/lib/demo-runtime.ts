import {
  Deployment,
  Repository,
  deploymentSteps,
  repositories as demoRepositories,
  terminalLines,
} from "@/lib/mock-data";

export const DEFAULT_PROJECT_ID = "web-app";
export const DEFAULT_NAMESPACE = `zeroops-${DEFAULT_PROJECT_ID}`;
export const DEFAULT_HOST = `${DEFAULT_PROJECT_ID}.zeroops.dev`;
export const DEFAULT_LIVE_URL = `https://${DEFAULT_HOST}`;

export interface AnalysisResult {
  framework: string;
  version: string;
  language: string;
  confidence: number;
  resources: {
    cpu: string;
    memory: string;
    storage: string;
  };
  risk_score: number;
  dependencies: string[];
  vulnerabilities: string[];
  dockerfile: string;
  kubernetes_manifest: string;
}

export interface DeploymentRecord extends Omit<Deployment, "commit" | "image"> {
  commit?: string;
  image?: string;
  namespace?: string;
  liveUrl?: string;
}

export type TerminalLine = (typeof terminalLines)[number];

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

export function fallbackRepositories(): Repository[] {
  return demoRepositories;
}

export function createFallbackAnalysis(repo = "acme/web-app"): AnalysisResult {
  const projectId = normalizeProjectId(repo);
  const namespace = namespaceForProject(projectId);
  const host = hostForProject(projectId);

  return {
    framework: "Next.js",
    version: "16.2.6",
    language: "TypeScript",
    confidence: 96,
    resources: {
      cpu: "200m",
      memory: "256Mi",
      storage: "1Gi",
    },
    risk_score: 18,
    dependencies: [
      "next@16.2.6",
      "react@19.2.4",
      "tailwindcss@4",
      "framer-motion@12.40.0",
      "lucide-react@1.16.0",
      "typescript@5",
    ],
    vulnerabilities: [
      "No blocking vulnerabilities detected in production path",
      "Recommend rotating demo GitHub token before production use",
      "Enable image signing before enterprise rollout",
    ],
    dockerfile: [
      "FROM node:20-alpine",
      "WORKDIR /app",
      "COPY package*.json ./",
      "RUN npm ci",
      "COPY . .",
      "RUN npm run build",
      "EXPOSE 3000",
      "CMD [\"npm\", \"start\"]",
    ].join("\n"),
    kubernetes_manifest: [
      "apiVersion: apps/v1",
      "kind: Deployment",
      "metadata:",
      `  name: ${projectId}`,
      `  namespace: ${namespace}`,
      "---",
      "apiVersion: v1",
      "kind: Service",
      "metadata:",
      `  name: ${projectId}-svc`,
      `  namespace: ${namespace}`,
      "---",
      "apiVersion: networking.k8s.io/v1",
      "kind: Ingress",
      "metadata:",
      `  name: ${projectId}-ingress`,
      `  namespace: ${namespace}`,
      "  annotations:",
      "    cert-manager.io/cluster-issuer: letsencrypt-prod",
      "spec:",
      "  ingressClassName: nginx",
      "  tls:",
      "  - hosts:",
      `    - ${host}`,
      "---",
      "apiVersion: autoscaling/v2",
      "kind: HorizontalPodAutoscaler",
    ].join("\n"),
  };
}

export function createDeploymentRecord(repo = "acme/web-app", id?: string): DeploymentRecord {
  const projectId = normalizeProjectId(repo);
  return {
    id: id || `dep-${Date.now().toString(36)}`,
    app: projectId,
    repo,
    environment: "production",
    status: "building",
    duration: "0s",
    deployedBy: "AI Auto-Deploy",
    time: "Just now",
    version: "v1.0.0",
    commit: "demo",
    image: `acr.azurecr.io/${projectId}:v1.0.0`,
    namespace: namespaceForProject(projectId),
    liveUrl: liveUrlForProject(projectId),
  };
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

export function createSimulatedSteps() {
  return deploymentSteps.map((step) => ({ ...step, status: "completed" as const }));
}

export function createLiveLogLine(index: number, pod = `${DEFAULT_PROJECT_ID}-7d4f`) {
  const messages = [
    "GET /api/v1/deployments 200 23ms",
    "Health probe passed on /readyz",
    "Pulled secret project-secrets from namespace cache",
    "HPA recommendation stable at 4 replicas",
    "Ingress controller synced TLS certificate",
    "POST /api/v1/deploy 201 156ms",
    "RBAC check passed for role=project-admin",
  ];
  const levels = ["INFO", "INFO", "DEBUG", "INFO", "INFO", "INFO", "DEBUG"] as const;
  const messageIndex = index % messages.length;
  const timestamp = new Date().toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return {
    id: `fallback-log-${Date.now()}-${index}`,
    timestamp,
    level: levels[messageIndex],
    pod,
    message: messages[messageIndex],
  };
}
