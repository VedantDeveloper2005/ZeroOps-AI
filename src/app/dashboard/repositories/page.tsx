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
} from "lucide-react";
import { useState, useEffect, useCallback, useRef } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { useAuth } from "@/lib/AuthContext";
import { useRouter } from "next/navigation";
import { api, getErrorMessage, type GitHubRepoItem } from "@/lib/api";

interface AnalysisResult {
  framework: string | null;
  runtime: string | null;
  packageManager: string | null;
  dockerSupport: boolean;
  databaseDependencies: string[];
  environmentVariables: string[];
  confidence: number | null;
  deploymentTarget: string | null;
  buildCommands: string | null;
  startCommands: string | null;
  port: string | null;
  explanation: string | null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
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

function toAnalysisResult(data: Record<string, unknown>, repo?: GitHubRepoItem): AnalysisResult {
  const recommendation = asRecord(data.deployment_recommendation);
  const fallbackExplanation = `AI matched ${repo?.full_name || "this repository"} to the best-fit deployment profile based on detected dependencies, runtime, and build requirements.`;
  return {
    framework: asString(data.framework),
    runtime: asString(data.runtime),
    packageManager: asString(data.package_manager),
    dockerSupport: data.docker_support === true,
    databaseDependencies: asStringArray(data.database_dependencies),
    environmentVariables: asStringArray(data.environment_variables),
    confidence: asNumber(data.confidence),
    deploymentTarget:
      asString(data.deployment_target) ||
      asString(data.deployment_strategy) ||
      asString(recommendation?.recommended_target),
    buildCommands: asString(data.build_commands) || asString(data.build_command),
    startCommands: asString(data.start_commands) || asString(data.start_command),
    port: asString(data.port),
    explanation: asString(data.explanation) || fallbackExplanation,
  };
}

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
    if (!selectedRepo || !isGitHubConnected) return;
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
  }, [selectedRepo, isGitHubConnected]);

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
      "Initializing analysis pipeline...",
      "Parsing repository configuration...",
      "Running dependency scan...",
      "Generating deployment report...",
      "Report ready.",
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
    if (onboardStep !== 2) {
      hasTriggeredAnalysis.current = false;
    }
  }, [onboardStep]);

  useEffect(() => {
    if (onboardStep !== 2 || !selectedRepo || hasTriggeredAnalysis.current) return;
    hasTriggeredAnalysis.current = true;
    setIsAnalyzing(true);
    const repoObj = gitRepos.find((repo) => repo.full_name === selectedRepo);
    setAnalysisResult(null);

    api
      .analyzeRepo(selectedRepo, selectedBranch)
      .then((data) => {
        setIsAnalyzing(false);
        setAnalysisResult(toAnalysisResult(data, repoObj));
        addToast("AI analysis complete.", "success");
      })
      .catch((err: unknown) => {
        setIsAnalyzing(false);
        setAnalysisResult(null);
        addToast(getErrorMessage(err, "Repository analysis failed."), "error");
      });
  }, [onboardStep, selectedRepo, selectedBranch, gitRepos, addToast]);

  const handleLaunchDeployment = async () => {
    if (!analysisResult) {
      addToast("Run repository analysis before deploying.", "error");
      return;
    }
    addToast(`Launching deployment for ${selectedRepo}...`, "info");
    try {
      const selectedRepoObj = gitRepos.find((repo) => repo.full_name === selectedRepo);
      const project = await api.createProject({
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
      addToast("Failed to initialize deployment pipeline.", "error");
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
          Deploy in three steps
        </h1>
        <p className="text-sm text-foreground-muted">
          Connect a repository, review the AI report, and launch.
        </p>

        <div className="flex items-center justify-center gap-2 pt-6 max-w-xl mx-auto overflow-x-auto no-scrollbar">
          {[
            { id: 1, label: "Select Repository" },
            { id: 2, label: "AI Analysis" },
            { id: 3, label: "Deploy" },
          ].map((step, idx) => (
            <div key={step.id} className="flex items-center flex-1 min-w-[120px]">
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
              {idx < 2 && (
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

      {!isGitHubConnected ? (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="glass rounded-2xl border border-border/40 p-8 text-center shadow-2xl max-w-md mx-auto space-y-6"
        >
          <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-lg">
            <GithubIcon size={28} className="text-white" />
          </div>
          <div className="space-y-2">
            <h3 className="text-xl font-bold text-foreground">Connect GitHub</h3>
            <p className="text-sm text-foreground-muted">
              ZeroOps needs access to your repositories to start deployments.
            </p>
          </div>

          <div className="pt-2">
            {isConnectingGit ? (
              <div className="space-y-3 p-4 rounded-xl bg-card border border-border text-center">
                <Loader2 size={24} className="animate-spin text-primary mx-auto" />
                <p className="text-xs font-mono text-foreground-muted">Redirecting to GitHub...</p>
              </div>
            ) : (
              <button
                onClick={() => {
                  setIsConnectingGit(true);
                  loginWithGitHub();
                }}
                className="w-full py-3 bg-primary text-white hover:bg-primary-hover font-semibold rounded-xl text-sm transition-all duration-200 cursor-pointer flex items-center justify-center gap-2"
              >
                <GithubIcon size={18} />
                Connect GitHub
              </button>
            )}
          </div>
        </motion.div>
      ) : (
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
                  <div className="grid md:grid-cols-2 gap-4 max-h-[380px] overflow-y-auto pr-1">
                    {filteredRepos.map((repo) => {
                      const isSelected = selectedRepo === repo.full_name;
                      return (
                        <motion.div
                          key={repo.id}
                          initial={{ opacity: 0, y: 5 }}
                          animate={{ opacity: 1, y: 0 }}
                          onClick={() => setSelectedRepo(repo.full_name)}
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
                          <div className="flex items-center gap-2 text-[10px] text-foreground-muted">
                            <span>{repo.language || "Unknown"}</span>
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

              <div className="flex justify-end pt-6 border-t border-border/40">
                <button
                  disabled={!selectedRepo}
                  onClick={() => setOnboardStep(2)}
                  className="px-5 py-2.5 bg-primary disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer flex items-center gap-1"
                >
                  Continue <ArrowRight size={14} />
                </button>
              </div>
            </div>
          )}

          {onboardStep === 2 && (
            <div className="space-y-6">
              <div className="flex items-center justify-between border-b border-border/40 pb-4">
                <div>
                  <h3 className="text-lg font-bold text-foreground">AI Analysis</h3>
                  <p className="text-xs text-foreground-muted">
                    ZeroOps AI is configuring your deployment automatically.
                  </p>
                </div>
                <span className="text-xs px-2.5 py-1 rounded-full bg-primary/10 text-primary border border-primary/20 font-mono font-semibold">
                  {selectedRepo.split("/").pop()}
                </span>
              </div>

              {isAnalyzing ? (
                <div className="space-y-6">
                  <div className="relative overflow-hidden bg-card border border-border rounded-2xl p-8 shadow-xl">
                    <div className="absolute inset-0 bg-gradient-to-tr from-primary/5 via-accent/5 to-transparent animate-pulse" />

                    <div className="relative flex justify-center mb-6">
                      <div className="w-14 h-14 flex items-center justify-center bg-primary/10 border border-primary/20 rounded-full">
                        <Brain size={24} className="text-primary animate-pulse" />
                      </div>
                    </div>

                    <div className="relative text-center mb-6">
                      <h4 className="text-sm font-bold text-foreground">Analyzing your repository...</h4>
                      <p className="text-xs text-foreground-muted mt-1">This usually takes a few seconds</p>
                    </div>

                    <div className="relative max-w-sm mx-auto space-y-3">
                      {scanChecklist.map((item, idx) => (
                        <motion.div
                          key={idx}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
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
                        {showScanLogs ? "Hide technical logs" : "View technical logs"}
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
                <div className="space-y-6">
                  <div className="grid md:grid-cols-2 gap-6">
                    <div className="glass rounded-xl p-6 border border-primary/20 bg-gradient-to-br from-primary/5 via-accent/5 to-transparent space-y-4">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
                          <Brain size={16} className="text-primary" />
                        </div>
                        <h4 className="text-xs font-bold text-primary uppercase tracking-wider">AI Deployment Report</h4>
                      </div>
                      <p className="text-xs text-foreground leading-relaxed">
                        {analysisResult?.explanation || "Analysis complete. Review the detected runtime and deployment plan below."}
                      </p>
                      <div className="p-3.5 bg-success/10 border border-success/20 rounded-xl flex items-center gap-2.5 text-xs text-success font-bold">
                        <Sparkles size={14} className="text-success" />
                        ZeroOps will auto-configure build, scaling, SSL, and runtime.
                      </div>
                    </div>

                    <div className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-4">
                      <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider border-b border-border/40 pb-2">
                        Detected Setup
                      </h4>
                      <div className="space-y-3.5 text-xs">
                        {[
                          { label: "Framework", value: analysisResult?.framework || "Not detected" },
                          { label: "Runtime", value: analysisResult?.runtime || "Not detected" },
                          { label: "Package Manager", value: analysisResult?.packageManager || "Not detected" },
                          {
                            label: "Database",
                            value: analysisResult?.databaseDependencies.length
                              ? analysisResult.databaseDependencies.join(", ")
                              : "None detected",
                          },
                          {
                            label: "Docker Support",
                            value: analysisResult?.dockerSupport ? "Yes" : "Not detected",
                          },
                          {
                            label: "Deployment Target",
                            value: analysisResult?.deploymentTarget || "Auto-selected",
                          },
                          {
                            label: "Confidence",
                            value: analysisResult?.confidence != null ? `${analysisResult.confidence}%` : "—",
                          },
                        ].map((item) => (
                          <div key={item.label} className="flex justify-between items-center py-1.5 border-b border-border/20 last:border-0">
                            <span className="text-foreground-muted font-semibold">{item.label}</span>
                            <span className="font-extrabold text-foreground text-right max-w-[60%]">
                              {item.value}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="grid md:grid-cols-2 gap-6">
                    <div className="bg-card border border-border rounded-xl p-5 space-y-3">
                      <h4 className="text-[11px] font-bold text-foreground-muted uppercase tracking-wider">
                        Auto-configured Commands
                      </h4>
                      <div className="space-y-2 text-xs text-foreground">
                        <div className="flex justify-between">
                          <span className="text-foreground-muted">Build</span>
                          <span className="font-mono">{analysisResult?.buildCommands || "Auto-detected"}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-foreground-muted">Start</span>
                          <span className="font-mono">{analysisResult?.startCommands || "Auto-detected"}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-foreground-muted">Port</span>
                          <span className="font-mono">{analysisResult?.port || "Auto-detected"}</span>
                        </div>
                      </div>
                    </div>

                    <div className="bg-card border border-border rounded-xl p-5 space-y-3">
                      <h4 className="text-[11px] font-bold text-foreground-muted uppercase tracking-wider">
                        Detected Environment Variables
                      </h4>
                      {analysisResult?.environmentVariables.length ? (
                        <div className="flex flex-wrap gap-2">
                          {analysisResult.environmentVariables.map((envVar) => (
                            <span
                              key={envVar}
                              className="px-2 py-1 rounded-full bg-background-secondary border border-border text-[10px] font-mono text-foreground"
                            >
                              {envVar}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-foreground-muted">No environment variables detected.</p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div className="flex justify-between pt-6 border-t border-border/40">
                <button
                  onClick={() => setOnboardStep(1)}
                  className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
                >
                  Back
                </button>
                <button
                  disabled={isAnalyzing || !analysisResult}
                  onClick={() => setOnboardStep(3)}
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
                  <h3 className="text-lg font-bold text-foreground">Deploy</h3>
                  <p className="text-xs text-foreground-muted">
                    ZeroOps will deploy with the AI-selected configuration.
                  </p>
                </div>
                <span className="text-xs px-2.5 py-1 rounded-full bg-success/10 text-success border border-success/20 font-medium">
                  Ready to deploy
                </span>
              </div>

              <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
                <div className="grid md:grid-cols-2 gap-4 text-xs">
                  <div className="space-y-1">
                    <p className="text-[10px] font-bold text-foreground-muted uppercase">Repository</p>
                    <p className="font-semibold text-foreground truncate">{selectedRepo}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-[10px] font-bold text-foreground-muted uppercase">Branch</p>
                    <p className="font-semibold text-foreground font-mono">{selectedBranch}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-[10px] font-bold text-foreground-muted uppercase">Framework</p>
                    <p className="font-semibold text-foreground">{analysisResult?.framework || "Not detected"}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-[10px] font-bold text-foreground-muted uppercase">Deployment Target</p>
                    <p className="font-semibold text-foreground">{analysisResult?.deploymentTarget || "Auto-selected"}</p>
                  </div>
                </div>
              </div>

              <div className="flex justify-between pt-6 border-t border-border/40">
                <button
                  onClick={() => setOnboardStep(2)}
                  className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
                >
                  Back
                </button>
                <button
                  onClick={handleLaunchDeployment}
                  disabled={!analysisResult}
                  className="px-5 py-2.5 bg-primary disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer flex items-center gap-1"
                >
                  <Rocket size={14} /> Deploy
                </button>
              </div>
            </div>
          )}
        </motion.div>
      )}
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
