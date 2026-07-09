"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight,
  Brain,
  Check,
  ChevronDown,
  ChevronUp,
  GitBranch,
  Loader2,
  Rocket,
  Search,
  Sparkles,
  AlertCircle,
  RefreshCw,
  Upload,
} from "lucide-react";
import { useState, useEffect, useCallback, useRef } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { useAuth } from "@/lib/AuthContext";
import { useRouter } from "next/navigation";
import { api, getErrorMessage, ApiError, type GitHubRepoItem } from "@/lib/api";

interface AnalysisResult {
  framework: string | null;
  runtime: string | null;
  packageManager: string | null;
  dockerSupport: boolean;
  databaseDependencies: string[];
  environmentVariables: string[];
  confidence: number | null;
  deploymentTarget: string | null;
  recommendedProvider?: string | null;
  recommendedTarget?: string | null;
  targetReason?: string | null;
  buildCommands: string | null;
  startCommands: string | null;
  port: string | null;
  explanation: string | null;
  estimated_cost?: string;
  compute_cost?: number;
  database_cost?: number;
  platform_fee?: number;
  bandwidth_cost?: number;
  monitoring_cost?: number;
  total_cost?: number;
  projected_growth_cost?: number;
  why_this_plan?: string;
  recommended_compute_tier?: string;
  detected_vars_detail?: Array<{
    key: string;
    type: string;
    is_missing: boolean;
    has_default: boolean;
    default_val: string;
  }>;
  application_type?: string | null;
  estimated_build_time?: string | null;
  production_readiness_score?: number | null;
  detected_services?: string[];
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function toAnalysisResult(data: Record<string, unknown>): AnalysisResult {
  const databaseDependencies = asStringArray(data.database_dependencies);
  const detectedServices = asStringArray(data.detected_services);

  return {
    framework: asString(data.framework),
    runtime: asString(data.runtime),
    packageManager: asString(data.package_manager),
    dockerSupport: data.docker_support === true,
    databaseDependencies,
    environmentVariables: asStringArray(data.environment_variables),
    confidence: asNumber(data.confidence),
    deploymentTarget: asString(data.deployment_target) || asString(data.deployment_strategy),
    recommendedProvider: asString(data.recommended_provider),
    recommendedTarget: asString(data.recommended_target),
    targetReason: asString(data.target_reason),
    buildCommands: asString(data.build_commands) || asString(data.build_command),
    startCommands: asString(data.start_commands) || asString(data.start_command),
    port: asString(data.port),
    explanation: asString(data.explanation),
    estimated_cost: asString(data.estimated_cost) || undefined,
    compute_cost: asNumber(data.compute_cost) ?? undefined,
    database_cost: asNumber(data.database_cost) ?? undefined,
    platform_fee: asNumber(data.platform_fee) ?? undefined,
    total_cost: asNumber(data.total_cost) ?? undefined,
    projected_growth_cost: asNumber(data.projected_growth_cost) ?? undefined,
    why_this_plan: asString(data.why_this_plan) || undefined,
    recommended_compute_tier: asString(data.recommended_compute_tier) || undefined,
    detected_vars_detail: Array.isArray(data.detected_vars_detail) ? data.detected_vars_detail : undefined,
    application_type: asString(data.application_type),
    estimated_build_time: asString(data.estimated_build_time),
    production_readiness_score: asNumber(data.production_readiness_score),
    detected_services: detectedServices,
  };
}

const displayValue = (value?: string | number | null, fallback = "Not detected") =>
  value === undefined || value === null || value === "" ? fallback : String(value);

const formatDate = (value?: string | null) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};

export default function RepositoriesPage() {
  const router = useRouter();
  const { user, loginWithGitHub } = useAuth();
  const { addToast, addNotification, refreshProjects, refreshStats } = useNotifications();

  const [onboardStep, setOnboardStep] = useState(1);
  const [isConnectingGit, setIsConnectingGit] = useState(false);
  const [selectedRepo, setSelectedRepo] = useState("");
  const [uploadedProjectId, setUploadedProjectId] = useState<string | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isUploadingCode, setIsUploadingCode] = useState(false);
  const [selectedBranch, setSelectedBranch] = useState("main");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [gitRepos, setGitRepos] = useState<GitHubRepoItem[]>([]);
  const [isLoadingRepos, setIsLoadingRepos] = useState(false);
  const [repoSearchQuery, setRepoSearchQuery] = useState("");
  const [repoPage, setRepoPage] = useState(1);
  const [hasMoreRepos, setHasMoreRepos] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [availableBranches, setAvailableBranches] = useState<string[]>(["main"]);
  const [isLoadingBranches, setIsLoadingBranches] = useState(false);
  const [scanLogs, setScanLogs] = useState<string[]>([]);
  const [showScanLogs, setShowScanLogs] = useState(false);

  const scanPhrases = [
    "Connecting repository",
    "Analyzing dependencies",
    "Detecting framework and runtime",
    "Building deployment plan",
    "Finalizing AI report",
  ];
  const [scanStep, setScanStep] = useState(0);
  const scanChecklist = scanPhrases.map((phrase, idx) => ({
    label: phrase,
    done: scanStep > idx,
  }));

  const isGitHubConnected = user?.github_connected === true;
  const [oauthPending, setOauthPending] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setOauthPending(sessionStorage.getItem("zeroops.githubOAuth.pending") === "true");
  }, []);

  useEffect(() => {
    if (!isGitHubConnected || typeof window === "undefined") return;
    sessionStorage.removeItem("zeroops.githubOAuth.pending");
    setOauthPending(false);
    setIsConnectingGit(false);
  }, [isGitHubConnected]);

  const isGitHubAuthorizing = isConnectingGit || oauthPending;

  // Auto-advance to repository step if GitHub is already connected on load
  useEffect(() => {
    if (isGitHubConnected && onboardStep === 1) {
      setOnboardStep(2);
    }
  }, [isGitHubConnected, onboardStep]);

  const loadRepos = useCallback(
    async (searchQ?: string, page = 1) => {
      if (page === 1) {
        setIsLoadingRepos(true);
      } else {
        setIsLoadingMore(true);
      }
      try {
        const result = await api.getGitHubRepos({
          page,
          per_page: 30,
          sort: "updated",
          q: searchQ || undefined,
        });
        if (page === 1) {
          setGitRepos(result.repos);
        } else {
          setGitRepos((prev) => [...prev, ...result.repos]);
        }
        setHasMoreRepos(result.has_next);
        setRepoPage(page);
        if (result.repos.length > 0 && !selectedRepo) {
          setSelectedRepo(result.repos[0].full_name);
        }
      } catch (err) {
        console.error("Failed to load GitHub repos:", err);
        addToast("Failed to load repositories from GitHub", "error");
      } finally {
        setIsLoadingRepos(false);
        setIsLoadingMore(false);
      }
    },
    [selectedRepo, addToast]
  );

  useEffect(() => {
    if (!isGitHubConnected) return;
    const timer = setTimeout(() => {
      loadRepos(repoSearchQuery, 1);
    }, 400);
    return () => clearTimeout(timer);
  }, [repoSearchQuery, isGitHubConnected, loadRepos]);

  useEffect(() => {
    if (!selectedRepo || !isGitHubConnected || uploadedProjectId) return;
    setIsLoadingBranches(true);
    api
      .getRepoBranches(selectedRepo)
      .then((res) => {
        setAvailableBranches(res.branches.length > 0 ? res.branches : ["main"]);
        setSelectedBranch(res.branches.includes("main") ? "main" : res.branches[0] || "main");
      })
      .catch(() => {
        setAvailableBranches(["main"]);
        setSelectedBranch("main");
      })
      .finally(() => setIsLoadingBranches(false));
  }, [selectedRepo, isGitHubConnected, uploadedProjectId]);

  useEffect(() => {
    if (isGitHubConnected) {
      loadRepos();
    }
  }, [isGitHubConnected, loadRepos]);

  useEffect(() => {
    if (!isAnalyzing) {
      setScanLogs([]);
      setScanStep(0);
      return;
    }
    const logs = [
      "Requesting repository metadata from backend...",
      "Reading package and runtime configuration...",
      "Checking detected environment variable references...",
      "Saving analysis results to your workspace...",
      "Waiting for backend response...",
    ];
    let idx = 0;
    setScanLogs([logs[0]]);
    setScanStep(1);
    const timer = setInterval(() => {
      idx += 1;
      if (idx < logs.length) {
        setScanLogs((prev) => [...prev, logs[idx]]);
        setScanStep((step) => Math.min(scanPhrases.length, step + 1));
      } else {
        clearInterval(timer);
      }
    }, 600);
    return () => clearInterval(timer);
  }, [isAnalyzing, scanPhrases.length]);

  const hasTriggeredAnalysis = useRef(false);
  useEffect(() => {
    if (onboardStep !== 3) {
      hasTriggeredAnalysis.current = false;
    }
  }, [onboardStep]);

  const [analysisError, setAnalysisError] = useState<{ error: string; details: string; stage: string } | null>(null);

  const runAnalysis = useCallback(() => {
    if (!selectedRepo) return;
    setIsAnalyzing(true);
    setAnalysisResult(null);
    setAnalysisError(null);

    api
      .analyzeRepo(selectedRepo, selectedBranch)
      .then((data) => {
        setIsAnalyzing(false);
        setAnalysisResult(toAnalysisResult(data));
        setAnalysisError(null);
        addToast("AI analysis complete.", "success");
      })
      .catch((err: unknown) => {
        setIsAnalyzing(false);
        setAnalysisResult(null);
        if (err instanceof ApiError && err.details && typeof err.details === "object") {
          const details = err.details as { error?: unknown; details?: unknown; stage?: unknown };
          setAnalysisError({
            error: typeof details.error === "string" ? details.error : "Analysis Failed",
            details: typeof details.details === "string" ? details.details : err.message,
            stage: typeof details.stage === "string" ? details.stage : "repository_analysis"
          });
        } else {
          setAnalysisError({
            error: "Analysis Failed",
            details: getErrorMessage(err, "An unexpected error occurred during repository analysis."),
            stage: "repository_analysis"
          });
        }
        addToast("Repository analysis failed.", "error");
      });
  }, [selectedRepo, selectedBranch, addToast]);

  useEffect(() => {
    if (onboardStep !== 3 || !selectedRepo || uploadedProjectId || hasTriggeredAnalysis.current) return;
    hasTriggeredAnalysis.current = true;
    runAnalysis();
  }, [onboardStep, selectedRepo, uploadedProjectId, runAnalysis]);

  const handleLaunchDeployment = async () => {
    if (!analysisResult) {
      addToast("Run repository analysis before deploying.", "error");
      return;
    }
    try {
      const deploymentTargets = await api.getDeploymentTargets();
      if (!deploymentTargets.any_ready) {
        addToast("Configure Azure AKS or Google GKE before launching.", "warning");
        router.push("/dashboard/settings?tab=azure");
        return;
      }

      addToast(`Launching deployment for ${selectedRepo}...`, "info");
      const selectedRepoObj = gitRepos.find((repo) => repo.full_name === selectedRepo);
      const project = uploadedProjectId
        ? await api.getProject(uploadedProjectId)
        : await api.createProject({
            name: selectedRepo.split("/").pop() || selectedRepo,
            full_name: selectedRepo,
            repo_url: `https://github.com/${selectedRepo}`,
            framework: analysisResult.framework || "Unknown",
            language: selectedRepoObj?.language || "Unknown",
            branch: selectedBranch,
            region: "eastus",
          });

      const deployRes = await api.startDeployment({
        project_id: project.id,
        branch: selectedBranch,
        environment: "production",
      });

      await Promise.all([refreshProjects(), refreshStats()]);

      addToast("Deployment started.", "success");
      addNotification({
        title: "Deployment Pipeline Triggered",
        message: `Deployment started for ${selectedRepo}.`,
        type: "success",
        category: "deployment",
        action_url: `/dashboard/deployments?id=${deployRes.deployment_id}`,
      });

      router.push(`/dashboard/deployments?id=${deployRes.deployment_id}&repo=${encodeURIComponent(selectedRepo)}`);
    } catch (err) {
      console.error("Failed to deploy project:", err);
      addToast(getErrorMessage(err, "Failed to initialize deployment pipeline."), "error");
    }
  };

  const handleUploadCode = async () => {
    if (!uploadFile) {
      addToast("Choose a ZIP file before uploading.", "warning");
      return;
    }

    setIsUploadingCode(true);
    setAnalysisError(null);
    try {
      const result = await api.uploadCode(uploadFile);
      setUploadedProjectId(result.project.id);
      setSelectedRepo(result.project.full_name);
      setSelectedBranch(result.project.branch || "uploaded");
      setAvailableBranches([result.project.branch || "uploaded"]);
      setAnalysisResult(toAnalysisResult(result.analysis));
      setOnboardStep(4);
      await Promise.all([refreshProjects(), refreshStats()]);
      addToast("Code uploaded and analyzed.", "success");
    } catch (err) {
      console.error("Code upload failed:", err);
      addToast(getErrorMessage(err, "Failed to upload code."), "error");
    } finally {
      setIsUploadingCode(false);
    }
  };

  const filteredRepos = gitRepos.filter((repo) =>
    repo.full_name.toLowerCase().includes(repoSearchQuery.toLowerCase()) ||
    repo.name.toLowerCase().includes(repoSearchQuery.toLowerCase())
  );
  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="text-center space-y-2 mb-8">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-[10px] font-bold uppercase tracking-wider">
          <Sparkles size={12} /> ZeroOps Deploy
        </div>
        <h1 className="text-3xl font-extrabold text-foreground tracking-tight">
          Deploy in four steps
        </h1>
        <p className="text-sm text-foreground-muted">
          Connect GitHub, select your repository, run AI analysis, and deploy.
        </p>

        <div className="flex items-center justify-center gap-2 pt-6 max-w-2xl mx-auto overflow-x-auto no-scrollbar">
          {[
            { id: 1, label: "Connect GitHub" },
            { id: 2, label: "Select Repository" },
            { id: 3, label: "AI Analysis" },
            { id: 4, label: "Review & Deploy" },
          ].map((step, idx) => (
            <div key={step.id} className="flex items-center flex-1 min-w-[100px]">
              <div className="flex flex-col items-center gap-1.5 flex-1">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs border transition-all duration-300 ${
                    onboardStep === step.id
                      ? "bg-primary border-primary text-white"
                      : onboardStep > step.id
                        ? "bg-success/20 border-success text-success"
                        : "bg-card border-border text-foreground-muted"
                  }`}
                >
                  {onboardStep > step.id ? <Check size={14} /> : step.id}
                </div>
                <span
                  className={`text-[10px] font-bold transition-colors duration-300 whitespace-nowrap ${
                    onboardStep === step.id ? "text-foreground" : "text-foreground-muted"
                  }`}
                >
                  {step.label}
                </span>
              </div>
              {idx < 3 && (
                <div
                  className={`h-px flex-1 -mt-4 mx-2 transition-all duration-300 ${
                    onboardStep > step.id ? "bg-success/40" : "bg-border"
                  }`}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      <motion.div
        key={onboardStep}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        transition={{ duration: 0.25 }}
        className="glass rounded-2xl border border-border/40 p-6 md:p-8 shadow-2xl space-y-6"
      >
        {onboardStep === 1 && (
          <div className="space-y-6">
            <div className="flex items-center justify-between border-b border-border/40 pb-4">
              <div>
                <h3 className="text-lg font-bold text-foreground">Connect GitHub</h3>
                <p className="text-xs text-foreground-muted">
                  ZeroOps needs access to your repositories to start deployments.
                </p>
              </div>
              <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${isGitHubConnected ? "bg-success/10 text-success border border-success/20" : "bg-warning/10 text-warning border border-warning/20"}`}>
                {isGitHubConnected ? "Connected" : "Action Required"}
              </span>
            </div>

            {!isGitHubConnected ? (
              <div className="p-6 bg-card border border-border rounded-xl text-center space-y-6 max-w-md mx-auto">
                <div className="w-12 h-12 mx-auto rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-lg">
                  <GithubIcon size={24} className="text-white" />
                </div>
                <div className="space-y-2">
                  <h4 className="text-sm font-bold text-foreground">Connect GitHub Account</h4>
                  <p className="text-xs text-foreground-muted">
                    Authorize ZeroOps to read repository layouts and commit states.
                  </p>
                </div>
                {isGitHubAuthorizing ? (
                  <div className="space-y-2 p-3 rounded-lg bg-background-secondary border border-border text-center">
                    <Loader2 size={20} className="animate-spin text-primary mx-auto" />
                    <p className="text-[10px] font-mono text-foreground-muted">Waiting for GitHub authorization...</p>
                  </div>
                ) : (
                  <button
                    onClick={() => {
                      setIsConnectingGit(true);
                      loginWithGitHub();
                    }}
                    className="w-full py-2.5 bg-primary text-white hover:bg-primary-hover font-semibold rounded-xl text-xs transition cursor-pointer flex items-center justify-center gap-2 shadow-lg shadow-primary/10"
                  >
                    <GithubIcon size={16} />
                    Sign in with GitHub
                  </button>
                )}
              </div>
            ) : (
              <div className="space-y-6">
                <div className="p-6 bg-card border border-border rounded-xl flex items-center gap-4">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary/30 to-accent/30 flex items-center justify-center font-bold text-foreground text-sm">
                    {user?.github_username?.substring(0, 2).toUpperCase() || "GH"}
                  </div>
                  <div>
                    <p className="text-sm font-bold text-foreground">@{user?.github_username}</p>
                    <p className="text-xs text-foreground-muted">GitHub integration is active and authorized.</p>
                  </div>
                  <div className="ml-auto text-success flex items-center gap-1 text-xs font-bold">
                    <Check size={16} /> Connected
                  </div>
                </div>
                <div className="flex justify-end pt-6 border-t border-border/40">
                  <button
                    onClick={() => setOnboardStep(2)}
                    className="px-5 py-2.5 bg-primary text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer flex items-center gap-1"
                  >
                    Continue to Repository <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {onboardStep === 2 && (
          <div className="space-y-6">
            <div className="flex items-center justify-between border-b border-border/40 pb-4">
              <div>
                <h3 className="text-lg font-bold text-foreground">Select repository</h3>
                <p className="text-xs text-foreground-muted">
                  Choose the repository you want to deploy.
                </p>
              </div>
              <span className="text-xs px-2.5 py-1 rounded-full bg-success/10 text-success border border-success/20 font-medium">
                @{user?.github_username}
              </span>
            </div>

            <div className="bg-background-secondary border border-border/80 rounded-xl px-4 py-2 flex items-center gap-2">
              <Search size={16} className="text-foreground-muted" />
              <input
                type="text"
                value={repoSearchQuery}
                onChange={(e) => setRepoSearchQuery(e.target.value)}
                placeholder="Search repositories..."
                className="bg-transparent border-none outline-none text-sm text-foreground placeholder:text-foreground-muted w-full"
              />
            </div>

            {isLoadingRepos ? (
              <div className="grid md:grid-cols-2 gap-3">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="p-4 rounded-xl border border-border bg-card/40 space-y-3 animate-pulse">
                    <div className="h-4 bg-background-secondary rounded w-24" />
                    <div className="h-3 bg-background-secondary rounded w-2/3" />
                  </div>
                ))}
              </div>
            ) : filteredRepos.length === 0 ? (
              <div className="p-8 text-center space-y-2 bg-card/20 border border-border/60 rounded-xl">
                <GitBranch size={32} className="text-foreground-muted mx-auto" />
                <p className="text-sm text-foreground-muted">No repositories match your search.</p>
              </div>
            ) : (
              <>
                <div className="grid md:grid-cols-2 gap-4 max-h-[300px] overflow-y-auto pr-1">
                  {filteredRepos.map((repo) => {
                    const isSelected = selectedRepo === repo.full_name;
                    return (
                      <motion.div
                        key={repo.id}
                        initial={{ opacity: 0, y: 5 }}
                        animate={{ opacity: 1, y: 0 }}
                        onClick={() => {
                          setUploadedProjectId(null);
                          setSelectedRepo(repo.full_name);
                          setAnalysisResult(null);
                        }}
                        className={`p-4 rounded-xl border transition-all cursor-pointer text-left space-y-2 ${
                          isSelected
                            ? "bg-primary-subtle/20 border-primary"
                            : "bg-card border-border hover:bg-card-hover"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-sm text-foreground truncate">{repo.name}</span>
                          <span className={`text-[9px] px-2 py-0.5 rounded-full font-bold ${repo.private ? "bg-zinc-800/80 border border-zinc-700 text-zinc-400" : "bg-primary/10 border border-primary/20 text-primary"}`}>
                            {repo.private ? "Private" : "Public"}
                          </span>
                        </div>
                        <p className="text-[11px] text-foreground-muted line-clamp-2">
                          {repo.description || "No description provided."}
                        </p>
                        <div className="flex items-center justify-between text-[10px] text-foreground-muted pt-1">
                          <span>{repo.language || "Unknown"}</span>
                          <span>•</span>
                          <span className="text-primary font-semibold">Ready to analyze</span>
                          <span>•</span>
                          <span>Updated {formatDate(repo.updated_at)}</span>
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
                {hasMoreRepos && (
                  <div className="text-center pt-2">
                    <button
                      onClick={() => loadRepos(repoSearchQuery, repoPage + 1)}
                      disabled={isLoadingMore}
                      className="text-xs text-primary hover:underline cursor-pointer disabled:opacity-50"
                    >
                      {isLoadingMore ? (
                        <span className="flex items-center gap-1.5 justify-center">
                          <Loader2 size={12} className="animate-spin" /> Loading more...
                        </span>
                      ) : (
                        "Load more repositories"
                      )}
                    </button>
                  </div>
                )}
              </>
            )}

            <div className="bg-card border border-border rounded-xl p-4 flex flex-col md:flex-row md:items-center gap-4">
              <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary flex-shrink-0">
                <Upload size={18} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-bold text-foreground">Upload code directly</p>
                <p className="text-[11px] text-foreground-muted">
                  Upload a ZIP archive when the project is not available through GitHub.
                </p>
              </div>
              <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
                <input
                  type="file"
                  accept=".zip,application/zip,application/x-zip-compressed"
                  onChange={(event) => setUploadFile(event.target.files?.[0] || null)}
                  className="block w-full max-w-[220px] text-[11px] text-foreground-muted file:mr-3 file:rounded-lg file:border file:border-border file:bg-background-secondary file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-foreground hover:file:bg-card"
                />
                <button
                  type="button"
                  onClick={handleUploadCode}
                  disabled={!uploadFile || isUploadingCode}
                  className="px-4 py-2 bg-card border border-border rounded-xl text-xs font-semibold text-foreground hover:bg-card-hover disabled:opacity-50 disabled:cursor-not-allowed transition flex items-center justify-center gap-1.5"
                >
                  {isUploadingCode ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
                  Upload
                </button>
              </div>
            </div>

            {selectedRepo && (
              <motion.div
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                className="p-4 rounded-xl border border-primary/20 bg-primary-subtle/5 flex items-center justify-between gap-4"
              >
                <div className="flex items-center gap-2">
                  <GitBranch size={14} className="text-primary" />
                  <span className="text-xs font-semibold text-foreground">Branch</span>
                </div>
                <div className="flex-1 max-w-[200px]">
                  {isLoadingBranches ? (
                    <div className="bg-card border border-border rounded-lg px-3 py-2 text-xs text-foreground-muted flex items-center gap-2">
                      <Loader2 size={12} className="animate-spin text-primary" /> Loading...
                    </div>
                  ) : (
                    <select
                      value={selectedBranch}
                      onChange={(e) => setSelectedBranch(e.target.value)}
                      className="w-full bg-card border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:border-primary focus:outline-none cursor-pointer font-mono"
                    >
                      {availableBranches.map((branch) => (
                        <option key={branch} value={branch}>
                          {branch}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </motion.div>
            )}

            <div className="flex justify-between pt-6 border-t border-border/40">
              <button
                onClick={() => setOnboardStep(1)}
                className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
              >
                Back
              </button>
              <button
                disabled={!selectedRepo}
                onClick={() => setOnboardStep(uploadedProjectId ? 2 : 3)}
                className="px-5 py-2.5 bg-primary disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer flex items-center gap-1"
              >
                Continue <ArrowRight size={14} />
              </button>
            </div>
          </div>
        )}

        {onboardStep === 3 && (
          <div className="space-y-6">
            <div className="flex items-center justify-between border-b border-border/40 pb-4">
              <div>
                <h3 className="text-lg font-bold text-foreground">AI Analysis</h3>
                <p className="text-xs text-foreground-muted">
                  {analysisError
                    ? "Repository analysis failed."
                    : "ZeroOps AI is reading the repository configuration."}
                </p>
              </div>
              <span className="text-xs px-2.5 py-1 rounded-full bg-primary/10 text-primary border border-primary/20 font-mono font-semibold">
                {selectedRepo.split("/").pop()}
              </span>
            </div>

            {analysisError ? (
              <div className="space-y-6">
                <div className="relative overflow-hidden bg-card border border-red-500/30 rounded-2xl p-6 md:p-8 shadow-xl text-center space-y-6">
                  <div className="absolute inset-0 bg-gradient-to-tr from-red-500/5 via-transparent to-transparent" />

                  <div className="relative flex justify-center">
                    <div className="w-14 h-14 flex items-center justify-center bg-red-500/10 border border-red-500/20 rounded-full text-red-500">
                      <AlertCircle size={24} />
                    </div>
                  </div>

                  <div className="relative space-y-2 max-w-md mx-auto">
                    <h4 className="text-sm font-bold text-foreground">{analysisError.error || "Analysis Failed"}</h4>
                    <p className="text-xs text-foreground-muted">
                      ZeroOps encountered an issue while retrieving or scanning the repository contents.
                    </p>
                    <div className="p-4 bg-zinc-950/80 rounded-xl border border-red-500/20 text-left space-y-1.5 mt-3 shadow-inner">
                      <span className="text-[10px] text-red-400 font-bold uppercase tracking-wider block">Reason:</span>
                      <p className="text-xs font-mono text-foreground leading-relaxed whitespace-pre-wrap">
                        {analysisError.details}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center justify-center gap-3 pt-2">
                    <button
                      onClick={() => {
                        setAnalysisError(null);
                        setOnboardStep(2);
                      }}
                      className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
                    >
                      Back
                    </button>
                    <button
                      onClick={runAnalysis}
                      className="px-5 py-2.5 bg-primary text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer flex items-center gap-1.5 shadow-lg shadow-primary/20"
                    >
                      <RefreshCw size={12} /> Retry
                    </button>
                  </div>
                </div>
              </div>
            ) : isAnalyzing ? (
              <div className="space-y-6">
                <div className="relative overflow-hidden bg-card border border-border rounded-2xl p-8 shadow-xl">
                  <div className="absolute inset-0 bg-gradient-to-tr from-primary/5 via-accent/5 to-transparent animate-pulse" />

                  <div className="relative flex justify-center mb-6">
                    <div className="w-14 h-14 flex items-center justify-center bg-primary/10 border border-primary/20 rounded-full">
                      <Brain size={24} className="text-primary animate-pulse" />
                    </div>
                  </div>

                  <div className="relative text-center mb-6">
                    <h4 className="text-sm font-bold text-foreground">Analyzing repository layout...</h4>
                    <p className="text-xs text-foreground-muted mt-1">Estimating runtime dependencies and configuration</p>
                  </div>

                  <div className="relative max-w-sm mx-auto space-y-3">
                    {scanChecklist.map((item, idx) => (
                      <motion.div
                        key={idx}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: idx * 0.15 }}
                        className="flex items-center gap-3 text-xs"
                      >
                        <div
                          className={`w-5 h-5 rounded-full flex items-center justify-center transition-all duration-500 ${
                            item.done
                              ? "bg-success/15 border border-success/30"
                              : "bg-card border border-border"
                          }`}
                        >
                          {item.done ? (
                            <Check size={12} className="text-success" />
                          ) : (
                            <Loader2 size={10} className="text-foreground-muted animate-spin" />
                          )}
                        </div>
                        <span
                          className={`font-medium transition-colors duration-300 ${
                            item.done ? "text-foreground" : "text-foreground-muted"
                          }`}
                        >
                          {item.label}
                        </span>
                      </motion.div>
                    ))}
                  </div>

                  <div className="relative mt-6 flex justify-center">
                    <button
                      onClick={() => setShowScanLogs((prev) => !prev)}
                      className="text-[10px] text-foreground-muted hover:text-foreground flex items-center gap-1 transition cursor-pointer"
                    >
                      {showScanLogs ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      {showScanLogs ? "Hide logs" : "View configuration logs"}
                    </button>
                  </div>

                  <AnimatePresence>
                    {showScanLogs && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="relative mt-3 overflow-hidden"
                      >
                        <div className="text-[11px] text-foreground-muted font-mono bg-zinc-950 p-4 rounded-xl border border-border/60 text-left space-y-2 max-h-[140px] overflow-y-auto no-scrollbar shadow-inner">
                          {scanLogs.map((log, index) => (
                            <div key={index} className="flex items-center gap-2">
                              <span className="text-primary select-none font-bold">›</span>
                              <span>{log}</span>
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </div>
            ) : (
              <div className="p-8 text-center bg-card border border-border rounded-xl space-y-4">
                <div className="w-12 h-12 mx-auto rounded-full bg-success/15 border border-success/30 flex items-center justify-center text-success">
                  <Check size={24} />
                </div>
                <div className="space-y-2">
                  <h4 className="text-sm font-bold text-foreground">Analysis Saved</h4>
                  <p className="text-xs text-foreground-muted">
                    The detected runtime, build commands, and required configuration were saved for review.
                  </p>
                </div>
              </div>
            )}

            <div className="flex justify-between pt-6 border-t border-border/40">
              <button
                onClick={() => setOnboardStep(2)}
                className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
              >
                Back
              </button>
              <button
                disabled={isAnalyzing || !analysisResult || Boolean(analysisError)}
                onClick={() => setOnboardStep(4)}
                className="px-5 py-2.5 bg-primary disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer flex items-center gap-1"
              >
                Continue to Plan <ArrowRight size={14} />
              </button>
            </div>
          </div>
        )}

        {onboardStep === 4 && (
          <div className="space-y-6">
            <div className="flex items-center justify-between border-b border-border/40 pb-4">
              <div>
                <h3 className="text-lg font-bold text-foreground">Review Deployment Plan</h3>
                <p className="text-xs text-foreground-muted">
                  Review detected runtime settings and complete required cloud/environment configuration before deploying.
                </p>
              </div>
              <span className="text-xs px-2.5 py-1 rounded-full bg-primary/10 text-primary border border-primary/20 font-medium">
                Review Required
              </span>
            </div>

            {/* Why This Plan? */}
            <div className="glass rounded-xl p-5 border border-primary/20 bg-gradient-to-br from-primary/5 to-transparent space-y-2">
              <h4 className="text-xs font-bold text-primary uppercase tracking-wider flex items-center gap-1.5">
                <Brain size={14} /> Why This Plan?
              </h4>
              <p className="text-xs text-foreground leading-relaxed">
                {analysisResult?.why_this_plan ||
                  "ZeroOps analyzed the repository and recorded only the configuration it could detect. Cloud targets, external databases, payment-gated AI fixes, and missing secrets must be confirmed before deployment starts."}
              </p>
            </div>

            <div className="grid md:grid-cols-2 gap-6">
              {/* Left Column: Blueprint & Database */}
              <div className="space-y-6">
                {/* Application Summary Sheet */}
                <div className="bg-card border border-border rounded-xl p-5 space-y-4">
                  <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider border-b border-border/40 pb-2">
                    Application Summary
                  </h4>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-3 text-[11px] leading-relaxed">
                    <div className="py-1 border-b border-border/10 col-span-2 flex justify-between">
                      <span className="text-foreground-muted font-bold">Repository</span>
                      <span className="font-extrabold text-foreground truncate max-w-[60%]">{selectedRepo}</span>
                    </div>
                    <div className="py-1 border-b border-border/10 flex justify-between">
                      <span className="text-foreground-muted font-bold">Branch</span>
                      <span className="font-mono text-foreground">{selectedBranch}</span>
                    </div>
                    <div className="py-1 border-b border-border/10 flex justify-between">
                      <span className="text-foreground-muted font-bold">Application Type</span>
                      <span className="font-extrabold text-foreground">{displayValue(analysisResult?.application_type)}</span>
                    </div>
                    <div className="py-1 border-b border-border/10 flex justify-between">
                      <span className="text-foreground-muted font-bold">Framework</span>
                      <span className="font-extrabold text-foreground">{displayValue(analysisResult?.framework)}</span>
                    </div>
                    <div className="py-1 border-b border-border/10 flex justify-between">
                      <span className="text-foreground-muted font-bold">Runtime</span>
                      <span className="font-extrabold text-foreground">{displayValue(analysisResult?.runtime)}</span>
                    </div>
                    <div className="py-1 border-b border-border/10 col-span-2 flex justify-between gap-3">
                      <span className="text-foreground-muted font-bold">Cloud Target</span>
                      <span className="font-extrabold text-foreground text-right truncate max-w-[60%]">
                        {displayValue(analysisResult?.recommendedTarget || analysisResult?.deploymentTarget, "Configure target")}
                      </span>
                    </div>
                    {analysisResult?.targetReason ? (
                      <div className="py-1 border-b border-border/10 col-span-2 flex justify-between gap-3">
                        <span className="text-foreground-muted font-bold">Target Reason</span>
                        <span className="font-medium text-foreground-muted text-right max-w-[70%]">
                          {analysisResult.targetReason}
                        </span>
                      </div>
                    ) : null}
                    <div className="py-1 border-b border-border/10 flex justify-between">
                      <span className="text-foreground-muted font-bold">Database</span>
                      <span className="font-extrabold text-foreground">
                        {analysisResult?.databaseDependencies && analysisResult.databaseDependencies.length > 0
                          ? analysisResult.databaseDependencies.join(", ")
                          : "None"}
                      </span>
                    </div>
                    <div className="py-1 border-b border-border/10 flex justify-between">
                      <span className="text-foreground-muted font-bold">Detected Services</span>
                      <span className="font-extrabold text-foreground">
                        {analysisResult?.detected_services && analysisResult.detected_services.length > 0
                          ? analysisResult.detected_services.join(", ")
                          : "Not detected"}
                      </span>
                    </div>
                    <div className="py-1 border-b border-border/10 flex justify-between">
                      <span className="text-foreground-muted font-bold">Required Variables</span>
                      <span className="font-extrabold text-foreground">
                        {analysisResult?.detected_vars_detail && analysisResult.detected_vars_detail.filter(v => v.type === "required").length > 0
                          ? `${analysisResult.detected_vars_detail.filter(v => v.type === "required").length} variables`
                          : "None"}
                      </span>
                    </div>
                    <div className="py-1 border-b border-border/10 flex justify-between">
                      <span className="text-foreground-muted font-bold">Estimated Build Time</span>
                      <span className="font-extrabold text-foreground">{displayValue(analysisResult?.estimated_build_time, "Not estimated")}</span>
                    </div>
                    <div className="py-1 border-b border-border/10 flex justify-between">
                      <span className="text-foreground-muted font-bold">Estimated Monthly Cost</span>
                      <span className="font-extrabold text-primary">{displayValue(analysisResult?.estimated_cost, "Not estimated")}</span>
                    </div>
                    <div className="py-1 border-b border-border/10 flex justify-between">
                      <span className="text-foreground-muted font-bold">Production Readiness</span>
                      <span className="font-extrabold text-success">
                        {analysisResult?.production_readiness_score != null ? `${analysisResult.production_readiness_score}%` : "Not scored"}
                      </span>
                    </div>
                    <div className="py-1 flex justify-between col-span-2 border-t border-border/10 pt-2">
                      <span className="text-foreground-muted font-bold">Deployment Confidence Score</span>
                      <span className="font-extrabold text-success">
                        {analysisResult?.confidence != null ? `${analysisResult.confidence}%` : "Not scored"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Databases Status Panel */}
                <div className="bg-card border border-border rounded-xl p-5 space-y-3">
                  <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider border-b border-border/40 pb-2">
                    Database Configuration
                  </h4>
                  {analysisResult?.databaseDependencies && analysisResult.databaseDependencies.length > 0 ? (
                    <div className="space-y-3">
                      {analysisResult.databaseDependencies.map((dbName) => (
                        <div key={dbName} className="p-3 rounded-lg bg-warning/5 border border-warning/20 flex items-start gap-2.5">
                          <AlertCircle size={16} className="text-warning mt-0.5" />
                          <div className="space-y-1">
                            <p className="text-xs font-bold text-warning">
                              {dbName} dependency detected
                            </p>
                            <p className="text-[11px] text-foreground-muted leading-relaxed">
                              Add a real database connection string in project environment settings before deployment. ZeroOps will not invent database credentials.
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="p-3 rounded-lg bg-zinc-800/30 border border-border/40 text-xs text-foreground-muted">
                      No database package or connection variable was detected by the scanner.
                    </div>
                  )}
                </div>
              </div>

              {/* Right Column: Pricing Engine */}
              <div className="bg-card border border-border rounded-xl p-5 flex flex-col justify-between space-y-4">
                <div className="space-y-4">
                  <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider border-b border-border/40 pb-2">
                    Cost Signals
                  </h4>
                  <div className="space-y-3 text-xs">
                    <div className="flex justify-between py-1 border-b border-border/10">
                      <span className="text-foreground-muted font-semibold">Compute Infrastructure</span>
                      <span className="font-bold text-foreground">
                        {analysisResult?.compute_cost != null ? `$${analysisResult.compute_cost}/month` : "Not estimated"}
                      </span>
                    </div>
                    {analysisResult?.database_cost && analysisResult.database_cost > 0 ? (
                      <div className="flex justify-between py-1 border-b border-border/10">
                        <span className="text-foreground-muted font-semibold">Managed Database Cost</span>
                        <span className="font-bold text-foreground">
                          ${analysisResult.database_cost}/month
                        </span>
                      </div>
                    ) : null}
                    <div className="flex justify-between py-1 border-b border-border/10">
                      <span className="text-foreground-muted font-semibold">ZeroOps Platform Margin</span>
                      <span className="font-bold text-foreground">
                        {analysisResult?.platform_fee != null ? `$${analysisResult.platform_fee}/month` : "Not estimated"}
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-border/10">
                      <span className="text-foreground-muted font-semibold">Bandwidth & Monitoring</span>
                      <span className="text-foreground-muted font-bold">Cloud billing dependent</span>
                    </div>
                    <div className="flex justify-between py-1.5 border-b border-primary/20 text-sm">
                      <span className="text-foreground font-bold">Estimated Monthly Total</span>
                      <span className="font-extrabold text-primary">
                        {analysisResult?.total_cost != null ? `$${analysisResult.total_cost}/month` : "Not estimated"}
                      </span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-foreground-muted">Projected Growth Limit</span>
                      <span className="font-semibold text-foreground-muted">
                        {analysisResult?.projected_growth_cost != null ? `$${analysisResult.projected_growth_cost.toFixed(0)}/month` : "Not estimated"}
                      </span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-foreground-muted">Recommended Compute Plan</span>
                      <span className="font-mono text-xs px-2 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-foreground font-bold">
                        {analysisResult?.recommended_compute_tier || "Not selected"}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="p-3 bg-primary/10 border border-primary/20 rounded-xl text-[11px] text-foreground-muted leading-relaxed">
                  <span className="font-bold text-foreground block mb-0.5">Billing Policy</span>
                  Production billing must be approved before AI code changes or automated remediation run. Cloud resource charges depend on the user&apos;s connected Azure or Google Cloud account.
                </div>
              </div>
            </div>

            {/* Environment Variables Table */}
            <div className="bg-card border border-border rounded-xl p-5 space-y-3">
              <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider border-b border-border/40 pb-2">
                Environment Variable Resolution
              </h4>
              <p className="text-[11px] text-foreground-muted">
                ZeroOps scanned package files and source configuration references. Missing external credentials must be supplied before deployment.
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left border-collapse">
                  <thead>
                    <tr className="border-b border-border text-foreground-muted font-bold text-[10px] uppercase">
                      <th className="py-2 pr-4">Variable Key</th>
                      <th className="py-2 px-4">Type</th>
                      <th className="py-2 px-4">Status</th>
                      <th className="py-2 pl-4">Required Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {analysisResult?.detected_vars_detail && analysisResult.detected_vars_detail.length > 0 ? (
                      analysisResult.detected_vars_detail.map((envVar) => (
                        <tr key={envVar.key}>
                          <td className="py-2 pr-4 font-mono font-bold text-foreground">{envVar.key}</td>
                          <td className="py-2 px-4">
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${envVar.type === "required" ? "bg-red-500/10 text-red-400 border border-red-500/20" : "bg-zinc-800 text-zinc-400 border border-zinc-700"}`}>
                              {envVar.type}
                            </span>
                          </td>
                          <td className="py-2 px-4">
                            {envVar.is_missing ? (
                              <span className="text-warning font-semibold">
                                {envVar.has_default ? "Generated securely" : "Needs value"}
                              </span>
                            ) : (
                              <span className="text-success font-semibold">Detected</span>
                            )}
                          </td>
                          <td className="py-2 pl-4 font-mono text-foreground-muted truncate max-w-[240px]">
                            {envVar.is_missing
                              ? envVar.has_default
                                ? "Server generated secret"
                                : "Configure in project settings"
                              : "Detected in repository"}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={4} className="py-4 text-center text-foreground-muted italic">
                          No environment variables were detected by the scanner.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="flex justify-between pt-6 border-t border-border/40">
              <button
                onClick={() => setOnboardStep(uploadedProjectId && analysisResult ? 4 : 3)}
                className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
              >
                Back
              </button>
              <button
                onClick={handleLaunchDeployment}
                disabled={!analysisResult}
                className="px-5 py-2.5 bg-primary disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer flex items-center gap-1.5 shadow-lg shadow-primary/20"
              >
                <Rocket size={14} className="animate-bounce" /> Deploy Application
              </button>
            </div>
          </div>
        )}
      </motion.div>
    </div>
  );
}

function GithubIcon({ size = 18, className }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" className={className}>
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
}
