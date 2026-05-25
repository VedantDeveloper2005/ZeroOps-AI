// ============================================
// ZeroOps Mock Data — Comprehensive dataset
// ============================================

export interface Deployment {
  id: string;
  app: string;
  repo: string;
  environment: "production" | "staging" | "development";
  status: "running" | "building" | "failed" | "stopped" | "healing";
  duration: string;
  deployedBy: string;
  time: string;
  commit: string;
  image: string;
  version: string;
}

export interface Repository {
  id: string;
  name: string;
  fullName: string;
  framework: string;
  language: string;
  lastCommit: string;
  lastCommitMessage: string;
  lastCommitAuthor: string;
  deploymentStatus: "running" | "building" | "failed" | "stopped";
  stars: number;
  totalDeployments: number;
}

export interface SecurityThreat {
  id: string;
  type: string;
  severity: "critical" | "high" | "medium" | "low";
  source: string;
  timestamp: string;
  status: "blocked" | "detected" | "resolved" | "investigating";
  description: string;
}

export interface AIAction {
  id: string;
  type: "scaling" | "security" | "deployment" | "optimization" | "healing" | "monitoring";
  message: string;
  timestamp: string;
  severity: "info" | "warning" | "success" | "critical";
  icon: string;
}

export interface Incident {
  id: string;
  title: string;
  severity: "critical" | "warning" | "resolved";
  affectedServices: string[];
  startTime: string;
  duration: string;
  status: "active" | "investigating" | "resolved";
  description: string;
}

export interface CostRecommendation {
  id: string;
  title: string;
  description: string;
  savings: string;
  type: "rightsize" | "idle" | "reserved" | "spot" | "consolidate";
  impact: "high" | "medium" | "low";
}

export interface InfraNode {
  id: string;
  name: string;
  type: "cluster" | "node" | "pod" | "service" | "deployment";
  status: "healthy" | "warning" | "critical";
  cpu: number;
  memory: number;
  connections: string[];
  x: number;
  y: number;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  level: "INFO" | "WARN" | "ERROR" | "DEBUG";
  pod: string;
  message: string;
}

export interface MetricPoint {
  time: string;
  value: number;
}

// ============================================
// DEPLOYMENTS
// ============================================

export const deployments: Deployment[] = [
  { id: "dep-001", app: "web-frontend", repo: "acme/web-app", environment: "production", status: "running", duration: "2m 34s", deployedBy: "AI Auto-Deploy", time: "2 min ago", commit: "a3f8c21", image: "acr.azurecr.io/web:v2.4.1", version: "v2.4.1" },
  { id: "dep-002", app: "api-gateway", repo: "acme/api-gateway", environment: "production", status: "running", duration: "1m 48s", deployedBy: "Vedant S.", time: "15 min ago", commit: "b7d2e09", image: "acr.azurecr.io/api:v3.1.0", version: "v3.1.0" },
  { id: "dep-003", app: "payments-service", repo: "acme/payments", environment: "staging", status: "building", duration: "0m 52s", deployedBy: "AI Auto-Deploy", time: "Just now", commit: "e1c4f87", image: "acr.azurecr.io/pay:v1.8.3", version: "v1.8.3" },
  { id: "dep-004", app: "auth-service", repo: "acme/auth", environment: "production", status: "running", duration: "3m 12s", deployedBy: "Sarah K.", time: "1 hour ago", commit: "d9a3b52", image: "acr.azurecr.io/auth:v2.0.0", version: "v2.0.0" },
  { id: "dep-005", app: "notification-svc", repo: "acme/notifications", environment: "development", status: "failed", duration: "4m 01s", deployedBy: "Vedant S.", time: "3 hours ago", commit: "f2e8a31", image: "acr.azurecr.io/notif:v0.9.2", version: "v0.9.2" },
  { id: "dep-006", app: "ml-pipeline", repo: "acme/ml-service", environment: "staging", status: "running", duration: "5m 22s", deployedBy: "AI Auto-Deploy", time: "5 hours ago", commit: "c4b7d19", image: "acr.azurecr.io/ml:v1.2.0", version: "v1.2.0" },
];

export const deploymentSteps = [
  { id: 1, label: "Cloning Repository", status: "completed" as const, duration: "4s" },
  { id: 2, label: "AI Analysis", status: "completed" as const, duration: "8s" },
  { id: 3, label: "Docker Image Build", status: "completed" as const, duration: "45s" },
  { id: 4, label: "K8s Manifest Generation", status: "completed" as const, duration: "3s" },
  { id: 5, label: "AKS Deployment", status: "active" as const, duration: "..." },
  { id: 6, label: "Ingress & Firewall", status: "pending" as const, duration: "" },
  { id: 7, label: "Autoscaling Setup", status: "pending" as const, duration: "" },
  { id: 8, label: "HTTPS & SSL", status: "pending" as const, duration: "" },
];

// ============================================
// REPOSITORIES
// ============================================

export const repositories: Repository[] = [
  { id: "repo-001", name: "web-app", fullName: "acme/web-app", framework: "Next.js", language: "TypeScript", lastCommit: "2 min ago", lastCommitMessage: "feat: add dashboard analytics", lastCommitAuthor: "Vedant S.", deploymentStatus: "running", stars: 142, totalDeployments: 48 },
  { id: "repo-002", name: "api-gateway", fullName: "acme/api-gateway", framework: "Express.js", language: "TypeScript", lastCommit: "15 min ago", lastCommitMessage: "fix: rate limiter config", lastCommitAuthor: "Sarah K.", deploymentStatus: "running", stars: 89, totalDeployments: 112 },
  { id: "repo-003", name: "payments", fullName: "acme/payments", framework: "FastAPI", language: "Python", lastCommit: "1 hour ago", lastCommitMessage: "chore: update stripe sdk", lastCommitAuthor: "Alex M.", deploymentStatus: "building", stars: 67, totalDeployments: 34 },
  { id: "repo-004", name: "auth", fullName: "acme/auth", framework: "NestJS", language: "TypeScript", lastCommit: "3 hours ago", lastCommitMessage: "feat: add oauth2 pkce flow", lastCommitAuthor: "Vedant S.", deploymentStatus: "running", stars: 56, totalDeployments: 78 },
  { id: "repo-005", name: "ml-service", fullName: "acme/ml-service", framework: "Flask", language: "Python", lastCommit: "1 day ago", lastCommitMessage: "feat: v2 recommendation engine", lastCommitAuthor: "Lisa T.", deploymentStatus: "running", stars: 203, totalDeployments: 23 },
];

// ============================================
// SECURITY
// ============================================

export const securityThreats: SecurityThreat[] = [
  { id: "threat-001", type: "DDoS Attempt", severity: "critical", source: "45.33.21.x", timestamp: "2 min ago", status: "blocked", description: "Large-scale distributed denial of service attempt detected and mitigated" },
  { id: "threat-002", type: "SQL Injection", severity: "high", source: "192.168.1.45", timestamp: "15 min ago", status: "blocked", description: "SQL injection attempt on /api/users endpoint" },
  { id: "threat-003", type: "Brute Force", severity: "medium", source: "103.42.89.x", timestamp: "1 hour ago", status: "blocked", description: "Multiple failed authentication attempts detected" },
  { id: "threat-004", type: "XSS Attempt", severity: "medium", source: "78.92.13.x", timestamp: "2 hours ago", status: "resolved", description: "Cross-site scripting attempt in comment field" },
  { id: "threat-005", type: "Port Scan", severity: "low", source: "212.47.xx.x", timestamp: "4 hours ago", status: "detected", description: "Systematic port scanning activity from external source" },
  { id: "threat-006", type: "Suspicious API Call", severity: "high", source: "Internal", timestamp: "6 hours ago", status: "investigating", description: "Unusual API call pattern from service account" },
];

export const blockedIPs = [
  { ip: "45.33.21.x", country: "Unknown", attacks: 1247, lastBlocked: "2 min ago" },
  { ip: "192.168.1.45", country: "US", attacks: 89, lastBlocked: "15 min ago" },
  { ip: "103.42.89.x", country: "CN", attacks: 456, lastBlocked: "1 hour ago" },
  { ip: "78.92.13.x", country: "RU", attacks: 23, lastBlocked: "2 hours ago" },
  { ip: "212.47.xx.x", country: "FR", attacks: 12, lastBlocked: "4 hours ago" },
];

export const complianceItems = [
  { name: "SOC 2 Type II", status: "compliant" as const, progress: 100, lastAudit: "2025-12-15" },
  { name: "HIPAA", status: "in-progress" as const, progress: 78, lastAudit: "2025-11-20" },
  { name: "GDPR", status: "compliant" as const, progress: 100, lastAudit: "2026-01-10" },
  { name: "ISO 27001", status: "in-progress" as const, progress: 65, lastAudit: "2025-10-05" },
];

// ============================================
// AI ACTIONS FEED
// ============================================

export const aiActions: AIAction[] = [
  { id: "ai-001", type: "scaling", message: "AI optimized scaling for api-gateway — 3→5 pods", timestamp: "2s ago", severity: "info", icon: "TrendingUp" },
  { id: "ai-002", type: "security", message: "Firewall rule applied: blocked 45.33.21.x (DDoS)", timestamp: "15s ago", severity: "critical", icon: "Shield" },
  { id: "ai-003", type: "deployment", message: "Rollback triggered for payments-service v2.3.1", timestamp: "1m ago", severity: "warning", icon: "RotateCcw" },
  { id: "ai-004", type: "security", message: "Suspicious traffic blocked from 103.42.89.x", timestamp: "2m ago", severity: "critical", icon: "AlertTriangle" },
  { id: "ai-005", type: "healing", message: "Pod api-gateway-7d4f restarted (OOMKilled)", timestamp: "3m ago", severity: "warning", icon: "RefreshCw" },
  { id: "ai-006", type: "healing", message: "Deployment healed: web-frontend scaled back to healthy", timestamp: "5m ago", severity: "success", icon: "Heart" },
  { id: "ai-007", type: "optimization", message: "Cost optimization: idle pod detected in staging", timestamp: "8m ago", severity: "info", icon: "DollarSign" },
  { id: "ai-008", type: "security", message: "SSL certificate renewed for app.zeroops.dev", timestamp: "12m ago", severity: "success", icon: "Lock" },
  { id: "ai-009", type: "scaling", message: "Traffic spike predicted — pre-scaling web-frontend", timestamp: "15m ago", severity: "info", icon: "Activity" },
  { id: "ai-010", type: "deployment", message: "Auto-deployed web-app v2.4.1 to production", timestamp: "18m ago", severity: "success", icon: "Rocket" },
  { id: "ai-011", type: "monitoring", message: "Latency anomaly detected in auth-service P99", timestamp: "22m ago", severity: "warning", icon: "BarChart3" },
  { id: "ai-012", type: "optimization", message: "Right-sized ml-pipeline: CPU 500m→200m (save $18/mo)", timestamp: "30m ago", severity: "success", icon: "Cpu" },
  { id: "ai-013", type: "security", message: "Vulnerability CVE-2026-1234 auto-patched in base image", timestamp: "45m ago", severity: "success", icon: "ShieldCheck" },
  { id: "ai-014", type: "scaling", message: "HPA adjusted: max replicas 10→15 for peak hours", timestamp: "1h ago", severity: "info", icon: "Maximize" },
  { id: "ai-015", type: "deployment", message: "Canary deployment validated — promoting to 100%", timestamp: "1.5h ago", severity: "success", icon: "CheckCircle" },
];

// ============================================
// INCIDENTS
// ============================================

export const incidents: Incident[] = [
  { id: "inc-001", title: "API Gateway High Latency", severity: "warning", affectedServices: ["api-gateway", "web-frontend"], startTime: "25 min ago", duration: "25m", status: "investigating", description: "P99 latency exceeded 500ms threshold on api-gateway" },
  { id: "inc-002", title: "Payment Service OOMKill", severity: "resolved", affectedServices: ["payments-service"], startTime: "2 hours ago", duration: "12m", status: "resolved", description: "payments-service pod killed due to memory limit exceeded. AI auto-scaled memory limits." },
  { id: "inc-003", title: "Database Connection Pool Exhaustion", severity: "resolved", affectedServices: ["auth-service", "api-gateway"], startTime: "1 day ago", duration: "8m", status: "resolved", description: "Connection pool maxed out during traffic spike. AI increased pool size and added connection recycling." },
  { id: "inc-004", title: "SSL Certificate Expiry Warning", severity: "resolved", affectedServices: ["web-frontend"], startTime: "3 days ago", duration: "1m", status: "resolved", description: "SSL certificate approaching expiry. AI auto-renewed via Azure Key Vault." },
];

// ============================================
// COST OPTIMIZATION
// ============================================

export const costRecommendations: CostRecommendation[] = [
  { id: "cost-001", title: "Right-size api-gateway", description: "Reduce CPU limit 500m→200m based on 30-day usage analysis", savings: "$18/mo", type: "rightsize", impact: "medium" },
  { id: "cost-002", title: "Enable Spot Instances for Staging", description: "Switch staging cluster nodes to spot instances for non-critical workloads", savings: "$45/mo", type: "spot", impact: "high" },
  { id: "cost-003", title: "Consolidate Idle Staging Pods", description: "3 pods in staging haven't received traffic in 72 hours", savings: "$22/mo", type: "idle", impact: "medium" },
  { id: "cost-004", title: "Reserved Pricing for Production", description: "Switch to 1-year reserved instances for stable production workloads", savings: "$42/mo", type: "reserved", impact: "high" },
  { id: "cost-005", title: "Optimize Container Images", description: "Multi-stage builds could reduce image sizes by 60%, saving on registry storage", savings: "$8/mo", type: "consolidate", impact: "low" },
];

export const idleResources = [
  { name: "staging-api", type: "Pod", lastActive: "72h ago", allocatedCpu: "500m", allocatedMemory: "512Mi", suggestedAction: "Scale to 0" },
  { name: "test-worker-2", type: "Pod", lastActive: "48h ago", allocatedCpu: "250m", allocatedMemory: "256Mi", suggestedAction: "Scale to 0" },
  { name: "dev-cache", type: "Pod", lastActive: "5 days ago", allocatedCpu: "100m", allocatedMemory: "128Mi", suggestedAction: "Delete" },
];

export const overprovisionedPods = [
  { pod: "api-gateway", allocatedCpu: "500m", usedCpu: "89m", allocatedMemory: "512Mi", usedMemory: "156Mi", savings: "$12/mo" },
  { pod: "ml-pipeline", allocatedCpu: "1000m", usedCpu: "234m", allocatedMemory: "2Gi", usedMemory: "890Mi", savings: "$28/mo" },
  { pod: "notification-svc", allocatedCpu: "250m", usedCpu: "45m", allocatedMemory: "256Mi", usedMemory: "67Mi", savings: "$6/mo" },
];

// ============================================
// INFRASTRUCTURE TOPOLOGY
// ============================================

export const infraNodes: InfraNode[] = [
  // Cluster
  { id: "cluster-1", name: "aks-prod-eastus", type: "cluster", status: "healthy", cpu: 67, memory: 72, connections: ["node-1", "node-2", "node-3"], x: 400, y: 80 },
  // Nodes
  { id: "node-1", name: "aks-nodepool1-vm0", type: "node", status: "healthy", cpu: 78, memory: 65, connections: ["pod-1", "pod-2", "pod-3", "pod-4"], x: 200, y: 220 },
  { id: "node-2", name: "aks-nodepool1-vm1", type: "node", status: "healthy", cpu: 54, memory: 71, connections: ["pod-5", "pod-6", "pod-7"], x: 400, y: 220 },
  { id: "node-3", name: "aks-nodepool1-vm2", type: "node", status: "warning", cpu: 91, memory: 88, connections: ["pod-8", "pod-9", "pod-10"], x: 600, y: 220 },
  // Pods
  { id: "pod-1", name: "web-frontend-7d4f", type: "pod", status: "healthy", cpu: 34, memory: 45, connections: ["svc-web"], x: 100, y: 380 },
  { id: "pod-2", name: "web-frontend-8e5g", type: "pod", status: "healthy", cpu: 28, memory: 41, connections: ["svc-web"], x: 180, y: 380 },
  { id: "pod-3", name: "api-gateway-a1b2", type: "pod", status: "healthy", cpu: 67, memory: 58, connections: ["svc-api"], x: 260, y: 380 },
  { id: "pod-4", name: "api-gateway-c3d4", type: "pod", status: "healthy", cpu: 72, memory: 62, connections: ["svc-api"], x: 340, y: 380 },
  { id: "pod-5", name: "auth-service-e5f6", type: "pod", status: "healthy", cpu: 45, memory: 52, connections: ["svc-auth"], x: 420, y: 380 },
  { id: "pod-6", name: "payments-g7h8", type: "pod", status: "warning", cpu: 89, memory: 84, connections: ["svc-pay"], x: 500, y: 380 },
  { id: "pod-7", name: "payments-i9j0", type: "pod", status: "healthy", cpu: 56, memory: 48, connections: ["svc-pay"], x: 580, y: 380 },
  { id: "pod-8", name: "ml-pipeline-k1l2", type: "pod", status: "healthy", cpu: 92, memory: 76, connections: ["svc-ml"], x: 660, y: 380 },
  { id: "pod-9", name: "notif-svc-m3n4", type: "pod", status: "critical", cpu: 12, memory: 95, connections: ["svc-notif"], x: 740, y: 380 },
  { id: "pod-10", name: "cache-redis-o5p6", type: "pod", status: "healthy", cpu: 22, memory: 38, connections: [], x: 820, y: 380 },
  // Services
  { id: "svc-web", name: "web-frontend-svc", type: "service", status: "healthy", cpu: 0, memory: 0, connections: ["svc-api"], x: 140, y: 500 },
  { id: "svc-api", name: "api-gateway-svc", type: "service", status: "healthy", cpu: 0, memory: 0, connections: ["svc-auth", "svc-pay", "svc-ml", "svc-notif"], x: 300, y: 500 },
  { id: "svc-auth", name: "auth-service-svc", type: "service", status: "healthy", cpu: 0, memory: 0, connections: [], x: 460, y: 500 },
  { id: "svc-pay", name: "payments-svc", type: "service", status: "warning", cpu: 0, memory: 0, connections: [], x: 540, y: 500 },
  { id: "svc-ml", name: "ml-pipeline-svc", type: "service", status: "healthy", cpu: 0, memory: 0, connections: [], x: 660, y: 500 },
  { id: "svc-notif", name: "notification-svc", type: "service", status: "critical", cpu: 0, memory: 0, connections: [], x: 740, y: 500 },
];

// ============================================
// LOGS
// ============================================

export const logEntries: LogEntry[] = [
  { id: "log-001", timestamp: "09:06:55.234", level: "INFO", pod: "api-gateway-a1b2", message: "GET /api/v1/deployments 200 23ms" },
  { id: "log-002", timestamp: "09:06:54.891", level: "INFO", pod: "web-frontend-7d4f", message: "Compiled successfully in 1.2s" },
  { id: "log-003", timestamp: "09:06:54.123", level: "WARN", pod: "payments-g7h8", message: "Connection pool reaching 80% capacity (40/50)" },
  { id: "log-004", timestamp: "09:06:53.456", level: "ERROR", pod: "notif-svc-m3n4", message: "Failed to send notification: SMTP connection timeout after 30s" },
  { id: "log-005", timestamp: "09:06:52.789", level: "INFO", pod: "auth-service-e5f6", message: "JWT token validated for user_id=usr_2847" },
  { id: "log-006", timestamp: "09:06:51.012", level: "DEBUG", pod: "ml-pipeline-k1l2", message: "Feature extraction completed: 1247 features, batch_size=64" },
  { id: "log-007", timestamp: "09:06:50.345", level: "INFO", pod: "api-gateway-c3d4", message: "POST /api/v1/deploy 201 156ms" },
  { id: "log-008", timestamp: "09:06:49.678", level: "WARN", pod: "cache-redis-o5p6", message: "Memory usage at 78% — consider scaling" },
  { id: "log-009", timestamp: "09:06:48.901", level: "INFO", pod: "web-frontend-8e5g", message: "Static assets served: 24 files, 1.8MB total" },
  { id: "log-010", timestamp: "09:06:47.234", level: "ERROR", pod: "payments-i9j0", message: "Stripe webhook signature verification failed" },
  { id: "log-011", timestamp: "09:06:46.567", level: "INFO", pod: "api-gateway-a1b2", message: "Rate limiter: 847/1000 requests in current window" },
  { id: "log-012", timestamp: "09:06:45.890", level: "DEBUG", pod: "auth-service-e5f6", message: "RBAC check passed for role=admin on resource=deployments" },
  { id: "log-013", timestamp: "09:06:44.123", level: "INFO", pod: "ml-pipeline-k1l2", message: "Model inference completed: prediction_score=0.94, latency=12ms" },
  { id: "log-014", timestamp: "09:06:43.456", level: "WARN", pod: "notif-svc-m3n4", message: "Retry attempt 2/3 for notification nid_8823" },
  { id: "log-015", timestamp: "09:06:42.789", level: "INFO", pod: "web-frontend-7d4f", message: "Server-side render completed: /dashboard 89ms" },
];

// ============================================
// METRICS DATA (time series)
// ============================================

export function generateMetricData(points: number, min: number, max: number, trend: "up" | "down" | "stable" = "stable"): MetricPoint[] {
  const data: MetricPoint[] = [];
  let current = (min + max) / 2;
  const pseudoRandom = (seed: number) => {
    const x = Math.sin(seed) * 10000;
    return x - Math.floor(x);
  };
  for (let i = 0; i < points; i++) {
    const seed = i + min + max + (trend === "up" ? 1 : trend === "down" ? 2 : 3);
    const noise = (pseudoRandom(seed) - 0.5) * (max - min) * 0.3;
    const trendBias = trend === "up" ? 0.5 : trend === "down" ? -0.5 : 0;
    current = Math.max(min, Math.min(max, current + noise + trendBias));
    const hour = Math.floor(i / (points / 24));
    data.push({
      time: `${String(hour).padStart(2, "0")}:${String((i * 60 / points * 24) % 60 | 0).padStart(2, "0")}`,
      value: Math.round(current * 10) / 10,
    });
  }
  return data;
}

export const cpuMetrics = generateMetricData(48, 20, 85, "stable");
export const memoryMetrics = generateMetricData(48, 40, 78, "up");
export const latencyMetrics = generateMetricData(48, 15, 120, "stable");
export const trafficMetrics = generateMetricData(48, 200, 1400, "up");
export const errorRateMetrics = generateMetricData(48, 0, 2.5, "stable");

// ============================================
// SYSTEM HEALTH
// ============================================

export const systemHealth = [
  { name: "Cluster Health", status: "healthy" as const, detail: "All nodes operational" },
  { name: "AI Engine", status: "healthy" as const, detail: "Processing 12 actions/min" },
  { name: "Security", status: "healthy" as const, detail: "No active threats" },
  { name: "Deploy Queue", status: "healthy" as const, detail: "3 queued" },
  { name: "Scaling Engine", status: "warning" as const, detail: "High utilization" },
  { name: "API Status", status: "healthy" as const, detail: "99.99% uptime" },
];

// ============================================
// DASHBOARD STATS
// ============================================

export const dashboardStats = [
  { label: "Active Deployments", value: "12", change: "+2", trend: "up" as const, color: "blue" },
  { label: "Deployment Health", value: "98.5%", change: "+0.3%", trend: "up" as const, color: "green" },
  { label: "Security Score", value: "94", change: "+2", trend: "up" as const, color: "cyan" },
  { label: "AI Recommendations", value: "3", change: "", trend: "neutral" as const, color: "purple" },
  { label: "Cost Estimate", value: "$342", change: "-$18", trend: "down" as const, color: "amber" },
  { label: "Error Alerts", value: "2", change: "+1", trend: "up" as const, color: "red" },
];

// ============================================
// SCALING DATA
// ============================================

export const scalingHistory = [
  { time: "09:00", event: "Scale Up", service: "web-frontend", from: 2, to: 4, trigger: "CPU > 75%" },
  { time: "08:30", event: "Scale Up", service: "api-gateway", from: 3, to: 5, trigger: "AI Prediction" },
  { time: "07:45", event: "Scale Down", service: "ml-pipeline", from: 4, to: 2, trigger: "Low Traffic" },
  { time: "06:00", event: "Scale Up", service: "payments-service", from: 2, to: 3, trigger: "Queue Length" },
  { time: "03:00", event: "Scale Down", service: "web-frontend", from: 4, to: 2, trigger: "Off-Peak" },
];

export const hpaStatus = {
  service: "web-frontend",
  minReplicas: 2,
  maxReplicas: 10,
  currentReplicas: 4,
  targetCPU: 70,
  currentCPU: 62,
  targetMemory: 80,
  currentMemory: 58,
};

// ============================================
// TRACING DATA
// ============================================

export const tracingSpans = [
  { id: "span-1", service: "api-gateway", operation: "GET /api/deployments", duration: 47, start: 0, color: "#3b82f6" },
  { id: "span-2", service: "auth-service", operation: "validateToken", duration: 8, start: 2, color: "#8b5cf6" },
  { id: "span-3", service: "api-gateway", operation: "fetchDeployments", duration: 28, start: 12, color: "#3b82f6" },
  { id: "span-4", service: "database", operation: "SELECT deployments", duration: 15, start: 14, color: "#06b6d4" },
  { id: "span-5", service: "cache-redis", operation: "GET cache:deployments", duration: 2, start: 13, color: "#f59e0b" },
  { id: "span-6", service: "api-gateway", operation: "serialize response", duration: 5, start: 40, color: "#3b82f6" },
];

// ============================================
// PRICING
// ============================================

export const pricingPlans = [
  {
    name: "Starter",
    price: "$29",
    yearlyPrice: "$24",
    description: "For individual developers and small projects",
    features: ["5 Deployments/month", "1 AKS Cluster", "Basic AI Analysis", "Community Support", "SSL Certificates", "Basic Monitoring"],
    cta: "Get Started",
    highlighted: false,
  },
  {
    name: "Pro",
    price: "$99",
    yearlyPrice: "$79",
    description: "For growing teams and production workloads",
    features: ["Unlimited Deployments", "5 AKS Clusters", "Advanced AI Analysis", "Priority Support", "Custom Domains", "Advanced Monitoring", "Autoscaling", "Security Center", "Cost Optimization"],
    cta: "Start Free Trial",
    highlighted: true,
  },
  {
    name: "Enterprise",
    price: "Custom",
    yearlyPrice: "Custom",
    description: "For organizations with complex infrastructure needs",
    features: ["Everything in Pro", "Unlimited Clusters", "Dedicated AI Engine", "24/7 Support + SLA", "SSO & SAML", "Compliance (SOC2/HIPAA)", "Custom Integrations", "Private Cloud Option", "Dedicated Account Manager"],
    cta: "Contact Sales",
    highlighted: false,
  },
];

// ============================================
// TERMINAL LOGS FOR DEPLOYMENT SIMULATION
// ============================================

export const terminalLines = [
  { text: "$ zeroops deploy --repo acme/web-app --env production", type: "command" as const },
  { text: "", type: "blank" as const },
  { text: "⚡ ZeroOps AI Engine v3.1.0", type: "info" as const },
  { text: "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", type: "info" as const },
  { text: "", type: "blank" as const },
  { text: "▸ Cloning repository acme/web-app...", type: "info" as const },
  { text: "  ✓ Repository cloned (1.2s)", type: "success" as const },
  { text: "", type: "blank" as const },
  { text: "▸ AI analyzing repository structure...", type: "info" as const },
  { text: "  ◆ Framework detected: Next.js 15.1.0", type: "info" as const },
  { text: "  ◆ Language: TypeScript (98.2%)", type: "info" as const },
  { text: "  ◆ Dependencies: 47 packages (3 vulnerabilities patched)", type: "warning" as const },
  { text: "  ◆ Estimated resources: 200m CPU, 256Mi Memory", type: "info" as const },
  { text: "  ✓ AI analysis complete (2.8s)", type: "success" as const },
  { text: "", type: "blank" as const },
  { text: "▸ Building Docker image...", type: "info" as const },
  { text: "  Step 1/8: FROM node:20-alpine", type: "info" as const },
  { text: "  Step 2/8: WORKDIR /app", type: "info" as const },
  { text: "  Step 3/8: COPY package*.json ./", type: "info" as const },
  { text: "  Step 4/8: RUN npm ci --production", type: "info" as const },
  { text: "  Step 5/8: COPY . .", type: "info" as const },
  { text: "  Step 6/8: RUN npm run build", type: "info" as const },
  { text: "  Step 7/8: EXPOSE 3000", type: "info" as const },
  { text: "  Step 8/8: CMD [\"npm\", \"start\"]", type: "info" as const },
  { text: "  ✓ Image built: acr.azurecr.io/web:v2.4.1 (34.2s)", type: "success" as const },
  { text: "  ✓ Image pushed to Azure Container Registry (8.1s)", type: "success" as const },
  { text: "", type: "blank" as const },
  { text: "▸ Generating Kubernetes manifests...", type: "info" as const },
  { text: "  ✓ Deployment manifest generated", type: "success" as const },
  { text: "  ✓ Service manifest generated", type: "success" as const },
  { text: "  ✓ HPA manifest generated (min: 2, max: 10)", type: "success" as const },
  { text: "", type: "blank" as const },
  { text: "▸ Deploying to AKS cluster aks-prod-eastus...", type: "info" as const },
  { text: "  ✓ Namespace zeroops-production created", type: "success" as const },
  { text: "  ✓ Deployment web-frontend applied (3 replicas)", type: "success" as const },
  { text: "  ✓ Service web-frontend-svc created", type: "success" as const },
  { text: "", type: "blank" as const },
  { text: "▸ Configuring ingress & firewall...", type: "info" as const },
  { text: "  ✓ Ingress rule created: app.zeroops.dev → web-frontend-svc:3000", type: "success" as const },
  { text: "  ✓ Azure Firewall rules applied (12 rules)", type: "success" as const },
  { text: "  ✓ DDoS protection enabled", type: "success" as const },
  { text: "", type: "blank" as const },
  { text: "▸ Setting up autoscaling...", type: "info" as const },
  { text: "  ✓ HPA configured: CPU target 70%, Memory target 80%", type: "success" as const },
  { text: "  ✓ AI-powered predictive scaling enabled", type: "success" as const },
  { text: "", type: "blank" as const },
  { text: "▸ Enabling HTTPS...", type: "info" as const },
  { text: "  ✓ SSL certificate provisioned via Let's Encrypt", type: "success" as const },
  { text: "  ✓ HTTPS redirect configured", type: "success" as const },
  { text: "", type: "blank" as const },
  { text: "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", type: "info" as const },
  { text: "✅ Deployment complete!", type: "success" as const },
  { text: "", type: "blank" as const },
  { text: "  🌐 URL:     https://app.zeroops.dev", type: "info" as const },
  { text: "  📦 Image:   acr.azurecr.io/web:v2.4.1", type: "info" as const },
  { text: "  ⏱  Time:    2m 34s", type: "info" as const },
  { text: "  🔒 SSL:     Enabled", type: "info" as const },
  { text: "  🛡  Firewall: Active (12 rules)", type: "info" as const },
  { text: "  📈 Scaling:  2-10 pods (AI-managed)", type: "info" as const },
];
