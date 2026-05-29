"use client";

import { motion } from "framer-motion";
import { GitBranch, Plus, Search, Play, Brain, Terminal, X, Loader2, Check, ArrowRight, Rocket, Lock, Star, ExternalLink, Trash2, Eye, EyeOff, AlertTriangle } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useState, useEffect, useCallback } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { useAuth } from "@/lib/AuthContext";
import { useRouter } from "next/navigation";
import { api, type Project, type GitHubRepoItem } from "@/lib/api";

const frameworkColors: Record<string, string> = {
  "Next.js": "bg-white/10 text-white",
  "Express.js": "bg-green-500/10 text-green-400",
  FastAPI: "bg-teal-500/10 text-teal-400",
  NestJS: "bg-red-500/10 text-red-400",
  Flask: "bg-blue-500/10 text-blue-400",
};
const langColors: Record<string, string> = {
  TypeScript: "bg-blue-500",
  Python: "bg-yellow-500",
  JavaScript: "bg-amber-400",
  Go: "bg-cyan-500",
  Rust: "bg-orange-600",
  Java: "bg-red-500",
  Ruby: "bg-red-400",
  PHP: "bg-indigo-400",
  "C#": "bg-purple-500",
  Swift: "bg-orange-400",
};

function detectFramework(lang: string | null): string {
  if (!lang) return "Unknown";
  const map: Record<string, string> = {
    TypeScript: "Next.js",
    JavaScript: "Express.js",
    Python: "FastAPI",
    Go: "Go Service",
    Rust: "Rust Service",
    Java: "Spring Boot",
    Ruby: "Rails",
    PHP: "Laravel",
    "C#": ".NET",
    Swift: "Vapor",
  };
  return map[lang] || lang;
}

function timeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

function calculateReadinessScore(repo: GitHubRepoItem): number {
  let score = 70; // baseline
  if (repo.description) score += 10;
  if (repo.default_branch === "main" || repo.default_branch === "master") score += 5;
  if (repo.language) {
    if (["TypeScript", "JavaScript", "Python"].includes(repo.language)) score += 15;
    else if (["Go", "Rust"].includes(repo.language)) score += 10;
    else score += 5;
  }
  if (repo.stargazers_count > 0) score += 5;
  return Math.min(100, score);
}

export default function RepositoriesPage() {
  const router = useRouter();
  const { user, loginWithGitHub } = useAuth();
  const { projects, refreshProjects, refreshStats, addToast, addNotification, hasDeployed } = useNotifications();

  // Onboarding Wizard local states
  const [onboardStep, setOnboardStep] = useState(1);
  const [isConnectingGit, setIsConnectingGit] = useState(false);
  const [selectedRepo, setSelectedRepo] = useState("");
  const [selectedBranch, setSelectedBranch] = useState("main");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  const [gitRepos, setGitRepos] = useState<GitHubRepoItem[]>([]);
  const [isLoadingRepos, setIsLoadingRepos] = useState(false);
  const [repoSearchQuery, setRepoSearchQuery] = useState("");
  const [repoPage, setRepoPage] = useState(1);
  const [hasMoreRepos, setHasMoreRepos] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [availableBranches, setAvailableBranches] = useState<string[]>(["main"]);
  const [isLoadingBranches, setIsLoadingBranches] = useState(false);
  const [scanLogs, setScanLogs] = useState<string[]>([]);

  // Env variables wizard state
  const [wizardEnvVars, setWizardEnvVars] = useState<{ key: string; value: string; is_secret: boolean }[]>([]);
  const [newEnvKey, setNewEnvKey] = useState("");
  const [newEnvVal, setNewEnvVal] = useState("");
  const [newEnvIsSecret, setNewEnvIsSecret] = useState(false);

  // Deployment config states
  const [region, setRegion] = useState("eastus");
  const [minReplicas, setMinReplicas] = useState(2);
  const [maxReplicas, setMaxReplicas] = useState(10);
  const [deployMode, setDeployMode] = useState("standard");
  const [detectedFramework, setDetectedFramework] = useState("Next.js");

  const [search, setSearch] = useState("");
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [repoName, setRepoName] = useState("");
  const [framework, setFramework] = useState("Next.js");
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Check if user logged in via GitHub
  const isGitHubConnected = user?.github_connected === true;

  // Load repositories on mount or search
  const loadRepos = useCallback(async (searchQ?: string, page = 1) => {
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
        setDetectedFramework(detectFramework(result.repos[0].language));
      }
    } catch (err) {
      console.error("Failed to load GitHub repos:", err);
      addToast("Failed to load repositories from GitHub", "error");
    } finally {
      setIsLoadingRepos(false);
      setIsLoadingMore(false);
    }
  }, [selectedRepo, addToast]);

  // Debounced search
  useEffect(() => {
    if (!isGitHubConnected) return;
    const timer = setTimeout(() => {
      loadRepos(repoSearchQuery, 1);
    }, 400);
    return () => clearTimeout(timer);
  }, [repoSearchQuery, isGitHubConnected, loadRepos]);

  // Load branches when a repo is selected
  useEffect(() => {
    if (!selectedRepo || !isGitHubConnected) return;
    setIsLoadingBranches(true);
    api.getRepoBranches(selectedRepo)
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

  // Auto load repos on mount
  useEffect(() => {
    if (isGitHubConnected && !hasDeployed) {
      loadRepos();
    }
  }, [isGitHubConnected, hasDeployed, loadRepos]);

  // Repository scanning progressive logs
  useEffect(() => {
    if (!isAnalyzing) {
      setScanLogs([]);
      return;
    }
    const logs = [
      "📡 Establishing secure connection to GitHub API...",
      "📂 Cloning repository tree structure...",
      "🔍 Scanning package definitions (package.json, requirements.txt, pyproject.toml)...",
      "🤖 Constructing codebase metadata payload...",
      "🚀 Querying GitHub Models (GPT-4.1) inference endpoint...",
      "✅ Mapping detected dependencies and database targets...",
      "📄 Generating optimized Dockerfile and Kubernetes manifests...",
      "🔒 Running repository risk and vulnerability checks..."
    ];
    let idx = 0;
    setScanLogs([logs[0]]);
    const timer = setInterval(() => {
      idx++;
      if (idx < logs.length) {
        setScanLogs((prev) => [...prev, logs[idx]]);
      } else {
        clearInterval(timer);
      }
    }, 1200);
    return () => clearInterval(timer);
  }, [isAnalyzing]);

  // Automatically trigger AI analysis when step 3 is reached
  useEffect(() => {
    if (onboardStep === 3 && selectedRepo) {
      setIsAnalyzing(true);
      const selectedRepoObj = gitRepos.find((r) => r.full_name === selectedRepo);
      api.analyzeRepo(selectedRepo, selectedBranch)
        .then((data: any) => {
          setIsAnalyzing(false);
          setAnalysisResult({
            framework: data.framework || detectedFramework,
            language: data.language || selectedRepoObj?.language || "TypeScript",
            runtime: data.runtime || "Node.js 20",
            packageManager: data.package_manager || "npm",
            dockerSupport: data.docker_support ?? false,
            monorepoStructure: data.monorepo_structure || "None",
            databaseDependencies: data.database_dependencies || [],
            deploymentStrategy: data.deployment_strategy || "Azure App Service",
            buildCommands: data.build_commands || "npm run build",
            startCommands: data.start_commands || "npm start",
            environmentVariables: data.environment_variables || [],
            riskScore: data.risk_score ?? 18,
            cpu: data.resources?.cpu || "200m",
            memory: data.resources?.memory || "256Mi",
            ports: data.port || "3000",
            vulnerabilities: data.vulnerabilities || [],
            deploymentRecommendation: data.deployment_recommendation || null,
          });
          
          if (data.environment_variables && data.environment_variables.length > 0) {
            setWizardEnvVars((prev) => {
              if (prev.length > 0) return prev;
              return data.environment_variables.map((v: string) => ({
                key: v,
                value: "",
                is_secret: v.toLowerCase().includes("secret") || v.toLowerCase().includes("key") || v.toLowerCase().includes("password") || v.toLowerCase().includes("token"),
              }));
            });
          }
          addToast("AI Analysis complete!", "success");
        })
        .catch(() => {
          setIsAnalyzing(false);
          setAnalysisResult({
            framework: detectedFramework,
            language: selectedRepoObj?.language || "TypeScript",
            runtime: "Node.js 20",
            packageManager: "npm",
            dockerSupport: false,
            monorepoStructure: "None",
            databaseDependencies: [],
            deploymentStrategy: "Azure App Service",
            buildCommands: "npm run build",
            startCommands: "npm start",
            environmentVariables: [],
            riskScore: 18,
            cpu: "200m",
            memory: "256Mi",
            ports: detectedFramework === "FastAPI" ? "8000" : "3000",
            vulnerabilities: [],
          });
          addToast("AI Analysis completed with local metadata.", "success");
        });
    }
  }, [onboardStep, selectedRepo, selectedBranch, detectedFramework, gitRepos, addToast]);

  const handleLaunchDeployment = async () => {
    addToast(`Launching deployment for ${selectedRepo}...`, "info");
    try {
      const selectedRepoObj = gitRepos.find((r) => r.full_name === selectedRepo);
      const proj = await api.createProject({
        name: selectedRepo.split("/").pop() || selectedRepo,
        full_name: selectedRepo,
        repo_url: `https://github.com/${selectedRepo}`,
        framework: detectedFramework,
        language: selectedRepoObj?.language || "TypeScript",
        branch: selectedBranch,
        region: region,
      });

      // Add environment variables
      if (wizardEnvVars.length > 0) {
        await Promise.all(
          wizardEnvVars.map(async (v) => {
            if (v.key.trim() && v.value.trim()) {
              try {
                await api.addEnvVar(proj.id, {
                  key: v.key.trim(),
                  value: v.value.trim(),
                  is_secret: v.is_secret,
                });
              } catch (err) {
                console.error(`Failed to save env var ${v.key}:`, err);
              }
            }
          })
        );
      }

      // Start deployment
      const deployRes = await api.startDeployment({
        project_id: proj.id,
        branch: selectedBranch,
        environment: "production",
      });

      await Promise.all([refreshProjects(), refreshStats()]);

      addToast("Project connected and deployment started!", "success");
      addNotification({
        title: "Deployment Pipeline Triggered",
        message: `Began building project ${selectedRepo} in region ${region}.`,
        type: "success",
        category: "deployment",
        action_url: `/dashboard/deployments/${deployRes.deployment_id}`,
      });

      router.push(
        `/dashboard/deployments?id=${deployRes.deployment_id}&repo=${encodeURIComponent(selectedRepo)}`
      );
    } catch (err) {
      console.error("Failed to deploy project in onboarding:", err);
      addToast("Failed to initialize deployment pipeline.", "error");
    }
  };

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoName.trim()) return;

    setIsSubmitting(true);
    const fullName = repoName.includes("/") ? repoName.trim() : `${user?.github_username || "user"}/${repoName.trim()}`;
    const name = fullName.split("/")[1] || fullName;

    try {
      await api.createProject({
        name,
        full_name: fullName,
        repo_url: `https://github.com/${fullName}`,
        framework,
        language: framework === "FastAPI" || framework === "Flask" ? "Python" : "TypeScript",
        branch: "main",
        region: "eastus",
      });
      await refreshProjects();
      setIsSubmitting(false);
      setIsModalOpen(false);
      setRepoName("");

      addToast(`Connected repository ${fullName} successfully!`, "success");
      addNotification({
        title: "Repository Connected",
        message: `Successfully connected ${fullName} (Framework: ${framework}).`,
        type: "success",
        category: "deployment",
        action_url: "/dashboard/repositories",
      });
    } catch (err) {
      console.error(err);
      addToast("Failed to connect repository", "error");
      setIsSubmitting(false);
    }
  };

  const handleCardAction = async (action: string, project: Project) => {
    const repo = project.full_name;
    if (action === "Analyze") {
      addToast(`Initiating AI security and performance review for ${repo}...`, "info");
      try {
        const data = await api.analyzeRepo(repo, "main");
        addToast(`AI scan complete. Framework: ${(data as any).framework}, Risk Score: ${(data as any).risk_score}`, "success");
        addNotification({
          title: "AI Analysis Complete",
          message: `Scan finished on ${repo}. Framework: ${(data as any).framework}. Recommended CPU: ${(data as any).resources?.cpu || "200m"}.`,
          type: "success",
          category: "ai",
          action_url: "/dashboard/ai-analysis",
        });
      } catch (err) {
        console.error("AI Analysis failed:", err);
        addToast(`AI Analysis failed for ${repo}.`, "error");
      }
    } else if (action === "Deploy") {
      addToast(`Triggering deployment pipeline for ${repo}...`, "info");
      try {
        const res = await api.startDeployment({
          project_id: project.id,
          branch: project.branch || "main",
          environment: "production",
        });
        addToast("Pipeline successfully initialized.", "success");
        router.push(`/dashboard/deployments?id=${res.deployment_id}&repo=${encodeURIComponent(repo)}`);
      } catch (err) {
        console.error("Deployment trigger failed:", err);
        addToast("Deployment trigger failed.", "error");
      }
    } else if (action === "Logs") {
      router.push("/dashboard/logs");
    }
  };

  const filtered = projects.filter(
    (p) =>
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.full_name.toLowerCase().includes(search.toLowerCase())
  );

  // ════════════════════════════════════════════════
  // ONBOARDING WIZARD (first-time users)
  // ════════════════════════════════════════════════
  if (!hasDeployed) {
    return (
      <div className="space-y-6 max-w-4xl mx-auto">
        {/* Onboarding Wizard Header */}
        <div className="text-center space-y-2 mb-8 animate-fade-in">
          <h1 className="text-3xl font-extrabold text-foreground tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-foreground to-foreground-muted">
            Onboarding Wizard
          </h1>
          <p className="text-sm text-foreground-muted">
            Set up your workspace and launch your first autonomic cloud deployment.
          </p>
          
          {/* Progress Indicators (6 Steps) */}
          <div className="flex items-center justify-center gap-2 pt-6 max-w-2xl mx-auto overflow-x-auto no-scrollbar">
            {[
              { id: 1, label: "Select Repo" },
              { id: 2, label: "Select Branch" },
              { id: 3, label: "AI Analysis" },
              { id: 4, label: "Env Variables" },
              { id: 5, label: "Target Config" },
              { id: 6, label: "Review & Deploy" },
            ].map((step, idx) => (
              <div key={step.id} className="flex items-center flex-1 min-w-[90px]">
                <div className="flex flex-col items-center gap-1.5 flex-1">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs border transition-all duration-300 ${
                      onboardStep === step.id
                        ? "bg-primary border-primary text-white glow-blue scale-110"
                        : onboardStep > step.id
                        ? "bg-success/20 border-success text-success"
                        : "bg-card border-border text-foreground-muted"
                    }`}
                  >
                    {onboardStep > step.id ? <Check size={14} /> : step.id}
                  </div>
                  <span
                    className={`text-[9px] font-bold transition-colors duration-300 whitespace-nowrap ${
                      onboardStep === step.id ? "text-foreground" : "text-foreground-muted"
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
                {idx < 5 && (
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

        {/* Git Connect Prerequisite State */}
        {!isGitHubConnected ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            className="glass rounded-2xl border border-border/40 p-8 text-center shadow-2xl max-w-md mx-auto space-y-6"
          >
            <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-lg glow-blue">
              <GithubIcon size={28} className="text-white" />
            </div>
            <div className="space-y-2">
              <h3 className="text-xl font-bold text-foreground">Connect GitHub Account</h3>
              <p className="text-sm text-foreground-muted">
                ZeroOps needs access to your GitHub account to retrieve your repositories and branches.
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
                  className="w-full py-3 bg-primary text-white hover:bg-primary-hover font-semibold rounded-xl text-sm transition-all duration-200 glow-blue cursor-pointer flex items-center justify-center gap-2"
                >
                  <GithubIcon size={18} />
                  Connect GitHub
                </button>
              )}
            </div>
          </motion.div>
        ) : (
          /* Wizard Steps Container */
          <motion.div
            key={onboardStep}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.25 }}
            className="glass rounded-2xl border border-border/40 p-6 md:p-8 shadow-2xl space-y-6"
          >
            {/* STEP 1: SELECT REPOSITORY */}
            {onboardStep === 1 && (
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b border-border/40 pb-4">
                  <div>
                    <h3 className="text-lg font-bold text-foreground">Select Repository</h3>
                    <p className="text-xs text-foreground-muted">
                      Select the project codebase you wish to configure and deploy.
                    </p>
                  </div>
                  <span className="text-xs px-2.5 py-1 rounded-full bg-success/10 text-success border border-success/20 font-medium">
                    @{user?.github_username}
                  </span>
                </div>

                {/* Search repos */}
                <div className="flex-1 bg-background-secondary border border-border/80 rounded-xl px-4 py-2.5 flex items-center gap-2">
                  <Search size={16} className="text-foreground-muted" />
                  <input
                    type="text"
                    value={repoSearchQuery}
                    onChange={(e) => setRepoSearchQuery(e.target.value)}
                    placeholder="Search your repositories..."
                    className="bg-transparent border-none outline-none text-sm text-foreground placeholder:text-foreground-muted w-full"
                  />
                </div>

                {isLoadingRepos ? (
                  <div className="grid md:grid-cols-3 gap-3">
                    {[1, 2, 3, 4, 5, 6].map((i) => (
                      <div key={i} className="p-4 rounded-xl border border-border bg-card/40 space-y-3 animate-pulse">
                        <div className="flex items-center justify-between">
                          <div className="h-4 bg-background-secondary rounded w-24" />
                          <div className="h-4 bg-background-secondary rounded-full w-12" />
                        </div>
                        <div className="space-y-1.5">
                          <div className="h-3 bg-background-secondary rounded w-full" />
                          <div className="h-3 bg-background-secondary rounded w-2/3" />
                        </div>
                        <div className="flex items-center justify-between pt-2">
                          <div className="h-3 bg-background-secondary rounded w-10" />
                          <div className="h-3 bg-background-secondary rounded w-14" />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : gitRepos.length === 0 ? (
                  <div className="p-8 text-center space-y-2 bg-card/20 border border-border/60 rounded-xl">
                    <GitBranch size={32} className="text-foreground-muted mx-auto" />
                    <p className="text-sm text-foreground-muted">No repositories found.</p>
                    {repoSearchQuery && (
                      <button
                        onClick={() => setRepoSearchQuery("")}
                        className="text-xs text-primary hover:underline cursor-pointer"
                      >
                        Clear search
                      </button>
                    )}
                  </div>
                ) : (
                  <>
                    <div className="grid md:grid-cols-3 gap-3 max-h-[320px] overflow-y-auto pr-1">
                      {gitRepos.map((repo) => {
                        const readiness = calculateReadinessScore(repo);
                        return (
                          <motion.div
                            key={repo.id}
                            initial={{ opacity: 0, y: 5 }}
                            animate={{ opacity: 1, y: 0 }}
                            onClick={() => {
                              setSelectedRepo(repo.full_name);
                              setDetectedFramework(detectFramework(repo.language));
                            }}
                            className={`p-4 rounded-xl border transition-all cursor-pointer text-left group ${
                              selectedRepo === repo.full_name
                                ? "bg-primary-subtle/20 border-primary shadow-lg scale-[1.01] bg-gradient-to-b from-card to-primary-subtle/5"
                                : "bg-card border-border hover:bg-card-hover hover:border-border/80"
                            }`}
                          >
                            <div className="flex items-center justify-between mb-1.5 flex-wrap gap-1.5">
                              <span className="font-semibold text-xs text-foreground truncate max-w-[130px]">
                                {repo.name}
                              </span>
                              <div className="flex items-center gap-1.5">
                                {repo.private && (
                                  <Lock size={10} className="text-foreground-muted" />
                                )}
                                {repo.language && (
                                  <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/10 text-foreground-muted font-medium">
                                    {repo.language}
                                  </span>
                                )}
                              </div>
                            </div>
                            <p className="text-[11px] text-foreground-muted line-clamp-2 min-h-[28px]">
                              {repo.description || "No description provided."}
                            </p>

                            <div className="mt-2.5 flex items-center justify-between">
                              <span className="text-[10px] text-foreground-muted">Readiness:</span>
                              <div className="flex items-center gap-1.5">
                                <div className="h-1.5 w-12 bg-background-secondary rounded-full overflow-hidden border border-border/40">
                                  <div
                                    className={`h-full rounded-full ${
                                      readiness >= 90 ? "bg-success" : readiness >= 80 ? "bg-warning" : "bg-danger"
                                    }`}
                                    style={{ width: `${readiness}%` }}
                                  />
                                </div>
                                <span className={`text-[10px] font-bold ${
                                  readiness >= 90 ? "text-success" : readiness >= 80 ? "text-warning" : "text-danger"
                                }`}>
                                  {readiness}%
                                </span>
                              </div>
                            </div>

                            <div className="flex items-center justify-between mt-2.5 pt-2 border-t border-border/20 text-[9px] text-foreground-muted">
                              <span className="flex items-center gap-0.5">
                                <Star size={9} /> {repo.stargazers_count}
                              </span>
                              <span>{timeAgo(repo.updated_at)}</span>
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

                <div className="flex justify-end pt-6 border-t border-border/40">
                  <button
                    disabled={!selectedRepo}
                    onClick={() => setOnboardStep(2)}
                    className="px-5 py-2.5 bg-primary disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer flex items-center gap-1"
                  >
                    Next <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            )}

            {/* STEP 2: SELECT BRANCH */}
            {onboardStep === 2 && (
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b border-border/40 pb-4">
                  <div>
                    <h3 className="text-lg font-bold text-foreground">Select Branch</h3>
                    <p className="text-xs text-foreground-muted">
                      Select which branch we should track and deploy to production.
                    </p>
                  </div>
                  <span className="text-xs px-2.5 py-1 rounded-full bg-primary/10 text-primary border border-primary/20 font-mono font-semibold">
                    {selectedRepo}
                  </span>
                </div>

                <div className="max-w-md mx-auto space-y-4 py-4">
                  <div>
                    <label className="block text-xs font-semibold text-foreground-muted mb-1.5">
                      Target Branch
                    </label>
                    {isLoadingBranches ? (
                      <div className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground-muted flex items-center gap-2">
                        <Loader2 size={14} className="animate-spin text-primary" /> Loading branches...
                      </div>
                    ) : (
                      <select
                        value={selectedBranch}
                        onChange={(e) => setSelectedBranch(e.target.value)}
                        className="w-full bg-card border border-border rounded-lg px-3 py-2.5 text-sm text-foreground focus:border-primary focus:outline-none cursor-pointer"
                      >
                        {availableBranches.map((b) => (
                          <option key={b} value={b}>
                            {b}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>

                  <div className="rounded-xl border border-border/40 bg-card/40 p-4 space-y-2 text-xs">
                    <p className="font-semibold text-foreground">Track Branch Deployments</p>
                    <p className="text-foreground-muted leading-relaxed">
                      ZeroOps monitors this branch. Pushing new commits will trigger automated testing, container builds, and canary updates.
                    </p>
                  </div>
                </div>

                <div className="flex justify-between pt-6 border-t border-border/40">
                  <button
                    onClick={() => setOnboardStep(1)}
                    className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
                  >
                    Back
                  </button>
                  <button
                    onClick={() => setOnboardStep(3)}
                    className="px-5 py-2.5 bg-primary text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer flex items-center gap-1"
                  >
                    Next <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            )}

            {/* STEP 3: AI CODE ANALYSIS */}
            {onboardStep === 3 && (
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b border-border/40 pb-4">
                  <div>
                    <h3 className="text-lg font-bold text-foreground">AI Codebase Analysis</h3>
                    <p className="text-xs text-foreground-muted">
                      ZeroOps scans your repository to detect dependencies, frameworks, runtimes, and ports.
                    </p>
                  </div>
                  <span className="text-xs px-2.5 py-1 rounded-full bg-primary/10 text-primary border border-primary/20 font-mono font-semibold">
                    {selectedRepo} @ {selectedBranch}
                  </span>
                </div>

                {isAnalyzing ? (
                  <div className="relative overflow-hidden bg-card border border-border rounded-2xl p-8 text-center space-y-6 shadow-xl">
                    {/* Rotating gradient background glow */}
                    <div className="absolute inset-0 bg-gradient-to-tr from-primary/5 via-accent/5 to-transparent animate-pulse" />
                    
                    {/* Spin and brain glow */}
                    <div className="relative mx-auto w-16 h-16 flex items-center justify-center bg-primary/10 border border-primary/20 rounded-full animate-bounce">
                      <Brain size={28} className="text-primary animate-pulse" />
                      <Loader2 size={64} className="absolute animate-spin text-primary/40" />
                    </div>

                    <div className="space-y-4 relative">
                      <div>
                        <h4 className="text-sm font-bold text-foreground">Analyzing Repository via GPT-4.1</h4>
                        <p className="text-xs text-foreground-muted">
                          GitHub Models is scanning files and structure for deployment architecture.
                        </p>
                      </div>
                      
                      {/* Terminal scanning log */}
                      <div className="text-[11px] text-foreground-muted font-mono max-w-lg mx-auto bg-zinc-950 p-4 rounded-xl border border-border/60 text-left space-y-2 max-h-[160px] overflow-y-auto no-scrollbar shadow-inner">
                        {scanLogs.map((log, index) => (
                          <div key={index} className="flex items-center gap-2 animate-fade-in">
                            <span className="text-primary select-none font-bold">›</span>
                            <span>{log}</span>
                            {index === scanLogs.length - 1 && (
                              <span className="w-1.5 h-3 bg-primary animate-ping" />
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-6">
                    <div className="grid md:grid-cols-2 gap-4">
                      {/* Left Card: Framework & Runtime */}
                      <div className="glass rounded-xl p-5 border border-border/60 space-y-3 bg-gradient-to-b from-card to-card/60">
                        <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider flex items-center gap-1.5">
                          <Brain size={14} className="text-primary" /> Framework & Runtime
                        </h4>
                        <div className="space-y-2.5 pt-1.5">
                          <div className="flex justify-between items-center text-xs">
                            <span className="text-foreground-muted">Detected Framework</span>
                            <span className="font-semibold text-foreground">{analysisResult?.framework}</span>
                          </div>
                          <div className="flex justify-between items-center text-xs">
                            <span className="text-foreground-muted">Language</span>
                            <span className="font-semibold text-foreground">{analysisResult?.language}</span>
                          </div>
                          <div className="flex justify-between items-center text-xs">
                            <span className="text-foreground-muted">Runtime Environment</span>
                            <span className="font-semibold text-foreground font-mono bg-background-secondary px-2 py-0.5 rounded border border-border/60">
                              {analysisResult?.runtime}
                            </span>
                          </div>
                          <div className="flex justify-between items-center text-xs">
                            <span className="text-foreground-muted">Package Manager</span>
                            <span className="font-semibold text-foreground">{analysisResult?.packageManager}</span>
                          </div>
                        </div>
                      </div>

                      {/* Right Card: Build & Strategy */}
                      <div className="glass rounded-xl p-5 border border-border/60 space-y-3 bg-gradient-to-b from-card to-card/60">
                        <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider flex items-center gap-1.5">
                          <Terminal size={14} className="text-primary" /> Build & Execution Settings
                        </h4>
                        <div className="space-y-2.5 pt-1.5">
                          <div className="flex justify-between items-center text-xs">
                            <span className="text-foreground-muted">Docker Support</span>
                            <span className={`font-semibold ${analysisResult?.dockerSupport ? "text-success" : "text-foreground-muted"}`}>
                              {analysisResult?.dockerSupport ? "Yes (Dockerfile)" : "No (Auto-built)"}
                            </span>
                          </div>
                          <div className="flex justify-between items-center text-xs">
                            <span className="text-foreground-muted">Deployment Target</span>
                            <span className="font-semibold text-foreground">{analysisResult?.deploymentStrategy}</span>
                          </div>
                          <div className="flex justify-between items-center text-xs">
                            <span className="text-foreground-muted">Build Command</span>
                            <span className="font-mono text-[10px] text-foreground bg-background-secondary px-1.5 py-0.5 rounded border border-border/40 truncate max-w-[150px]">
                              {analysisResult?.buildCommands}
                            </span>
                          </div>
                          <div className="flex justify-between items-center text-xs">
                            <span className="text-foreground-muted">Start Command</span>
                            <span className="font-mono text-[10px] text-foreground bg-background-secondary px-1.5 py-0.5 rounded border border-border/40 truncate max-w-[150px]">
                              {analysisResult?.startCommands}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="grid md:grid-cols-2 gap-4">
                      {/* Left: Databases */}
                      <div className="glass rounded-xl p-5 border border-border/60 space-y-2">
                        <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider">
                          Databases & Integrations
                        </h4>
                        <div className="flex flex-wrap gap-2 pt-1">
                          {analysisResult?.databaseDependencies?.length > 0 && analysisResult.databaseDependencies[0] !== "None" ? (
                            analysisResult.databaseDependencies.map((db: string) => (
                              <span key={db} className="text-[10px] font-mono px-2 py-1 rounded bg-accent/10 border border-accent/20 text-accent font-semibold">
                                {db}
                              </span>
                            ))
                          ) : (
                            <span className="text-xs text-foreground-muted">No database dependencies detected.</span>
                          )}
                        </div>
                      </div>

                      {/* Right: Cognitive Limits Recommendation */}
                      <div className="glass rounded-xl p-5 border border-border/60 space-y-2">
                        <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider">
                          Resource Recommendations
                        </h4>
                        <div className="grid grid-cols-2 gap-3 pt-1">
                          <div className="bg-background-secondary/50 p-2 rounded border border-border/40 text-center">
                            <p className="text-[9px] uppercase tracking-wide text-foreground-muted font-semibold">CPU Limit</p>
                            <p className="text-sm font-bold text-foreground mt-0.5">{analysisResult?.cpu}</p>
                          </div>
                          <div className="bg-background-secondary/50 p-2 rounded border border-border/40 text-center">
                            <p className="text-[9px] uppercase tracking-wide text-foreground-muted font-semibold">Memory Limit</p>
                            <p className="text-sm font-bold text-foreground mt-0.5">{analysisResult?.memory}</p>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Vulnerabilities warnings */}
                    {analysisResult?.vulnerabilities?.length > 0 && (
                      <div className="p-4 rounded-xl border border-warning/20 bg-warning/5 space-y-2 animate-fade-in">
                        <p className="text-xs font-semibold text-warning flex items-center gap-1.5">
                          <AlertTriangle size={14} /> Security Audit Recommendations
                        </p>
                        <ul className="list-disc pl-4 space-y-1 text-[11px] text-foreground-muted">
                          {analysisResult.vulnerabilities.map((v: string, idx: number) => (
                            <li key={idx}>{v}</li>
                          ))}
                        </ul>
                      </div>
                    )}
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
                    disabled={isAnalyzing}
                    onClick={() => setOnboardStep(4)}
                    className="px-5 py-2.5 bg-primary disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer flex items-center gap-1"
                  >
                    Next <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            )}

            {/* STEP 4: ENVIRONMENT VARIABLES */}
            {onboardStep === 4 && (
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b border-border/40 pb-4">
                  <div>
                    <h3 className="text-lg font-bold text-foreground">Environment Variables</h3>
                    <p className="text-xs text-foreground-muted">
                      Add key-value variables to be securely injected into your app runtime at deployment.
                    </p>
                  </div>
                  <span className="text-xs px-2.5 py-1 rounded-full bg-primary/10 text-primary border border-primary/20 font-mono font-semibold">
                    {selectedRepo}
                  </span>
                </div>

                {/* Env Var Add Form */}
                <div className="bg-card/40 border border-border/60 rounded-xl p-4 space-y-4">
                  <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider">
                    Add Environment Variable
                  </h4>
                  <div className="grid md:grid-cols-3 gap-3 items-end">
                    <div className="space-y-1.5">
                      <label className="block text-[10px] font-semibold text-foreground-muted">Key</label>
                      <input
                        type="text"
                        value={newEnvKey}
                        onChange={(e) => setNewEnvKey(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ""))}
                        placeholder="e.g. PORT or DATABASE_URL"
                        className="w-full bg-card border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:border-primary focus:outline-none placeholder:text-foreground-muted font-mono"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label className="block text-[10px] font-semibold text-foreground-muted">Value</label>
                      <input
                        type="text"
                        value={newEnvVal}
                        onChange={(e) => setNewEnvVal(e.target.value)}
                        placeholder="e.g. 8080 or connection_string"
                        className="w-full bg-card border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:border-primary focus:outline-none placeholder:text-foreground-muted font-mono"
                      />
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <label className="flex items-center gap-1.5 text-xs text-foreground-muted cursor-pointer select-none pb-2">
                        <input
                          type="checkbox"
                          checked={newEnvIsSecret}
                          onChange={(e) => setNewEnvIsSecret(e.target.checked)}
                          className="rounded border-border text-primary focus:ring-primary w-3.5 h-3.5 bg-card"
                        />
                        Secret / Masked
                      </label>
                      <button
                        type="button"
                        onClick={() => {
                          if (!newEnvKey.trim()) {
                            addToast("Variable Key cannot be empty.", "warning");
                            return;
                          }
                          if (wizardEnvVars.some((v) => v.key === newEnvKey.trim())) {
                            addToast(`Variable '${newEnvKey}' already added.`, "warning");
                            return;
                          }
                          setWizardEnvVars((prev) => [
                            ...prev,
                            { key: newEnvKey.trim(), value: newEnvVal, is_secret: newEnvIsSecret },
                          ]);
                          setNewEnvKey("");
                          setNewEnvVal("");
                          setNewEnvIsSecret(false);
                          addToast("Environment variable added.", "success");
                        }}
                        className="px-4 py-2 bg-primary text-white rounded-lg text-xs font-semibold hover:bg-primary-hover transition cursor-pointer flex items-center gap-1 shadow-sm h-[34px] mb-[1px]"
                      >
                        <Plus size={14} /> Add
                      </button>
                    </div>
                  </div>
                </div>

                {/* Env Var List */}
                <div className="space-y-2">
                  <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider">
                    Configured Variables ({wizardEnvVars.length})
                  </h4>
                  {wizardEnvVars.length === 0 ? (
                    <div className="p-6 text-center border border-dashed border-border rounded-xl text-xs text-foreground-muted">
                      No variables added yet. ZeroOps will fallback to default configurations.
                    </div>
                  ) : (
                    <div className="border border-border/60 rounded-xl overflow-hidden max-h-[220px] overflow-y-auto">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="bg-background-secondary border-b border-border/60 text-foreground-muted font-semibold">
                            <th className="p-3">Key</th>
                            <th className="p-3">Value</th>
                            <th className="p-3 text-center">Type</th>
                            <th className="p-3 text-center w-12">Action</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/40 bg-card/20">
                          {wizardEnvVars.map((v, idx) => (
                            <tr key={idx} className="hover:bg-card-hover/20">
                              <td className="p-3 font-mono font-semibold text-foreground truncate max-w-[150px]">{v.key}</td>
                              <td className="p-3 font-mono text-foreground-muted truncate max-w-[200px]">
                                {v.is_secret ? "••••••••" : v.value || "—"}
                              </td>
                              <td className="p-3 text-center">
                                <span className={`px-2 py-0.5 rounded text-[9px] font-semibold border ${
                                  v.is_secret
                                    ? "bg-warning/10 border-warning/20 text-warning"
                                    : "bg-success/10 border-success/20 text-success"
                                }`}>
                                  {v.is_secret ? "Secret" : "Plaintext"}
                                </span>
                              </td>
                              <td className="p-3 text-center">
                                <button
                                  type="button"
                                  onClick={() => {
                                    setWizardEnvVars((prev) => prev.filter((_, i) => i !== idx));
                                    addToast(`Removed ${v.key}`, "info");
                                  }}
                                  className="text-foreground-muted hover:text-danger transition-colors cursor-pointer"
                                >
                                  <Trash2 size={14} />
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                <div className="flex justify-between pt-6 border-t border-border/40">
                  <button
                    onClick={() => setOnboardStep(3)}
                    className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
                  >
                    Back
                  </button>
                  <button
                    onClick={() => setOnboardStep(5)}
                    className="px-5 py-2.5 bg-primary text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer flex items-center gap-1"
                  >
                    Next <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            )}

            {/* STEP 5: TARGET CONFIGURATION */}
            {onboardStep === 5 && (
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b border-border/40 pb-4">
                  <div>
                    <h3 className="text-lg font-bold text-foreground">Deployment Target Configuration</h3>
                    <p className="text-xs text-foreground-muted">
                      Select target cloud region, scaling triggers, and infrastructure strategies.
                    </p>
                  </div>
                  <span className="text-xs px-2.5 py-1 rounded-full bg-primary/10 text-primary border border-primary/20 font-mono font-semibold">
                    {selectedRepo}
                  </span>
                </div>

                <div className="grid md:grid-cols-3 gap-6">
                  {/* Left Column: Form Controls */}
                  <div className="md:col-span-2 space-y-6">
                    <div className="grid md:grid-cols-2 gap-4">
                      <div className="space-y-1.5">
                        <label className="block text-xs font-semibold text-foreground-muted">Target Azure Region</label>
                        <select
                          value={region}
                          onChange={(e) => setRegion(e.target.value)}
                          className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none cursor-pointer"
                        >
                          <option value="eastus">East US (Virginia)</option>
                          <option value="westus2">West US 2 (Washington)</option>
                          <option value="westeurope">West Europe (Amsterdam)</option>
                        </select>
                      </div>
                      <div className="space-y-1.5">
                        <label className="block text-xs font-semibold text-foreground-muted">Deployment Strategy</label>
                        <select
                          value={deployMode}
                          onChange={(e) => setDeployMode(e.target.value)}
                          className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none cursor-pointer"
                        >
                          <option value="standard">Rolling Update (Zero Downtime)</option>
                          <option value="canary">Canary Release (10% Traffic split)</option>
                          <option value="bluegreen">Blue/Green Deploy</option>
                        </select>
                      </div>
                    </div>

                    <div className="grid md:grid-cols-2 gap-4">
                      <div className="space-y-1.5">
                        <label className="block text-xs font-semibold text-foreground-muted">Min Pod Replicas</label>
                        <input
                          type="number"
                          min="1"
                          max="10"
                          value={minReplicas}
                          onChange={(e) => setMinReplicas(parseInt(e.target.value) || 1)}
                          className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <label className="block text-xs font-semibold text-foreground-muted">Max Pod Replicas</label>
                        <input
                          type="number"
                          min="1"
                          max="50"
                          value={maxReplicas}
                          onChange={(e) => setMaxReplicas(parseInt(e.target.value) || 10)}
                          className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
                        />
                      </div>
                    </div>

                    <div className="p-4 rounded-xl border border-primary/20 bg-primary/5 text-xs text-foreground-muted leading-relaxed">
                      <p className="font-semibold text-foreground mb-1">Autonomic Kubernetes Scaling</p>
                      ZeroOps configures Horizontal Pod Autoscalers (HPA) to scale between {minReplicas} and {maxReplicas} replicas, triggered dynamically at 70% aggregate CPU utilization.
                    </div>
                  </div>

                  {/* Right Column: AI Recommendations Display */}
                  <div className="glass rounded-xl p-5 border border-border bg-gradient-to-b from-primary/5 to-accent/5 space-y-4 flex flex-col justify-between shadow-md">
                    <div className="space-y-3">
                      <h4 className="text-xs font-bold text-primary flex items-center gap-1.5 uppercase tracking-wider">
                        <Brain size={14} /> AI Recommendations
                      </h4>
                      <p className="text-[11px] text-foreground-muted leading-relaxed">
                        Recommended deployment configuration generated by GitHub Models (GPT-4.1).
                      </p>

                      <div className="space-y-2.5 pt-2 text-xs">
                        <div className="border-b border-border/40 pb-2">
                          <p className="text-[9px] font-bold text-foreground-muted uppercase">Recommended Target</p>
                          <p className="mt-0.5 font-semibold text-foreground">
                            {analysisResult?.deploymentRecommendation?.recommended_target || analysisResult?.deploymentStrategy || "Azure App Service"}
                          </p>
                        </div>
                        <div className="border-b border-border/40 pb-2">
                          <p className="text-[9px] font-bold text-foreground-muted uppercase">Database Provisioning</p>
                          <p className="mt-0.5 font-semibold text-foreground">
                            {analysisResult?.deploymentRecommendation?.database_recommendation?.primary !== "None" 
                              ? "Azure Database for PostgreSQL" 
                              : "No Database Required"}
                          </p>
                        </div>
                        <div className="border-b border-border/40 pb-2">
                          <p className="text-[9px] font-bold text-foreground-muted uppercase">Auto-Scaling Limits</p>
                          <p className="mt-0.5 font-semibold text-foreground">
                            {analysisResult?.deploymentRecommendation?.scaling_recommendation?.min_replicas || 2} to {analysisResult?.deploymentRecommendation?.scaling_recommendation?.max_replicas || 10} replicas
                          </p>
                        </div>
                        <div>
                          <p className="text-[9px] font-bold text-foreground-muted uppercase">Est. Deployment Time</p>
                          <p className="mt-0.5 font-semibold text-success font-mono">
                            {analysisResult?.deploymentRecommendation?.estimated_deployment_time || "~2 minutes"}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="text-[9px] text-foreground-muted/60 text-center border-t border-border/40 pt-3 font-medium">
                      Generated by ZeroOps AI Analysis
                    </div>
                  </div>
                </div>

                <div className="flex justify-between pt-6 border-t border-border/40">
                  <button
                    onClick={() => setOnboardStep(4)}
                    className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
                  >
                    Back
                  </button>
                  <button
                    onClick={() => setOnboardStep(6)}
                    className="px-5 py-2.5 bg-primary text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer flex items-center gap-1"
                  >
                    Next <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            )}

            {/* STEP 6: REVIEW & DEPLOY */}
            {onboardStep === 6 && (
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b border-border/40 pb-4">
                  <div>
                    <h3 className="text-lg font-bold text-foreground">Review & Launch Deployment</h3>
                    <p className="text-xs text-foreground-muted">
                      Verify settings before launching your autonomous container deployment.
                    </p>
                  </div>
                  <span className="text-xs px-2.5 py-1 rounded-full bg-success/10 text-success border border-success/20 font-medium">
                    Ready to Deploy
                  </span>
                </div>

                <div className="grid md:grid-cols-2 gap-4">
                  {/* Left: Codebase Info */}
                  <div className="glass rounded-xl p-5 border border-border/60 space-y-3 bg-gradient-to-b from-card to-card/40">
                    <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider">
                      Source Code Details
                    </h4>
                    <div className="space-y-2 text-xs">
                      <div className="flex justify-between border-b border-border/10 pb-1.5">
                        <span className="text-foreground-muted">Repository</span>
                        <span className="font-semibold text-foreground truncate max-w-[180px]">{selectedRepo}</span>
                      </div>
                      <div className="flex justify-between border-b border-border/10 pb-1.5">
                        <span className="text-foreground-muted">Branch</span>
                        <span className="font-semibold text-foreground font-mono">{selectedBranch}</span>
                      </div>
                      <div className="flex justify-between border-b border-border/10 pb-1.5">
                        <span className="text-foreground-muted">Framework</span>
                        <span className="font-semibold text-foreground">{analysisResult?.framework}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-foreground-muted">Runtime</span>
                        <span className="font-semibold text-foreground font-mono">{analysisResult?.runtime}</span>
                      </div>
                    </div>
                  </div>

                  {/* Right: Cloud Config Info */}
                  <div className="glass rounded-xl p-5 border border-border/60 space-y-3 bg-gradient-to-b from-card to-card/40">
                    <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider">
                      Infrastructure Target
                    </h4>
                    <div className="space-y-2 text-xs">
                      <div className="flex justify-between border-b border-border/10 pb-1.5">
                        <span className="text-foreground-muted">Target region</span>
                        <span className="font-semibold text-foreground">{region === "eastus" ? "East US" : region === "westus2" ? "West US 2" : "West Europe"}</span>
                      </div>
                      <div className="flex justify-between border-b border-border/10 pb-1.5">
                        <span className="text-foreground-muted">Strategy</span>
                        <span className="font-semibold text-foreground capitalize">{deployMode} Deploy</span>
                      </div>
                      <div className="flex justify-between border-b border-border/10 pb-1.5">
                        <span className="text-foreground-muted">Scale Limits</span>
                        <span className="font-semibold text-foreground">{minReplicas} to {maxReplicas} Replicas</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-foreground-muted">Environment variables</span>
                        <span className="font-semibold text-foreground">{wizardEnvVars.length} variables</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex justify-between pt-6 border-t border-border/40">
                  <button
                    onClick={() => setOnboardStep(5)}
                    className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
                  >
                    Back
                  </button>
                  <button
                    onClick={handleLaunchDeployment}
                    className="px-6 py-3 bg-primary hover:bg-primary-hover text-white rounded-xl text-sm font-semibold transition glow-blue flex items-center gap-2 cursor-pointer"
                  >
                    <Rocket size={16} />
                    Launch Deployment
                  </button>
                </div>
              </div>
            )}
          </motion.div>
        )}
      </div>
    );
  }

  // ════════════════════════════════════════════════
  // POST-ONBOARDING: Connected Repositories View
  // ════════════════════════════════════════════════
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-end">
        <button
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary-hover transition-colors shadow-sm cursor-pointer"
        >
          <Plus size={16} /> Connect Repository
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Connected Projects", value: projects.length.toString(), icon: GitBranch },
          {
            label: "Active Deployments",
            value: projects
              .filter((p) => p.status === "deploying" || p.status === "active")
              .length.toString(),
            icon: Play,
          },
          {
            label: "Total Runs",
            value: projects.reduce((sum, p) => sum + (p.deployment_count || 0), 0).toString(),
            icon: Terminal,
          },
        ].map((s, i) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04 }}
            className="bg-card border border-border rounded-xl p-4 flex items-center gap-3 shadow-sm"
          >
            <div className="w-10 h-10 rounded-lg bg-primary-subtle flex items-center justify-center">
              <s.icon size={18} className="text-primary" />
            </div>
            <div>
              <p className="text-2xl font-bold text-foreground">{s.value}</p>
              <p className="text-xs text-foreground-muted">{s.label}</p>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Search */}
      <div className="flex gap-3">
        <div className="flex-1 bg-background-secondary border border-border/80 rounded-xl px-4 py-2.5 flex items-center gap-2">
          <Search size={16} className="text-foreground-muted" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search repositories..."
            className="bg-transparent border-none outline-none text-sm text-foreground placeholder:text-foreground-muted w-full"
          />
        </div>
      </div>

      {/* Repo cards */}
      <div className="grid lg:grid-cols-2 gap-4">
        {filtered.map((repo, i) => (
          <motion.div
            key={repo.id}
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04 }}
            className="bg-card border border-border rounded-xl p-5 hover:bg-card-hover/40 transition-all group shadow-sm"
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <GitBranch size={20} className="text-foreground-muted" />
                <div>
                  <h3 className="font-semibold text-foreground group-hover:text-primary transition-colors">
                    {repo.full_name}
                  </h3>
                  <p className="text-xs text-foreground-muted">Tracking branch: {repo.branch || "main"}</p>
                  <p className="text-[10px] text-foreground-muted mt-0.5">Region: {repo.region}</p>
                </div>
              </div>
              <StatusBadge status={repo.status || "active"} />
            </div>
            <div className="flex items-center gap-3 mb-4">
              <span
                className={`text-xs px-2 py-1 rounded-full ${
                  frameworkColors[repo.framework] || "bg-card text-foreground-muted"
                }`}
              >
                {repo.framework}
              </span>
              <span className="flex items-center gap-1 text-xs text-foreground-muted">
                <span className={`w-2.5 h-2.5 rounded-full ${langColors[repo.language] || "bg-gray-500"}`} />
                {repo.language}
              </span>
              <span className="text-xs text-foreground-muted">{repo.deployment_count || 0} deployments</span>
            </div>
            <div className="flex items-center gap-2">
              {[
                { icon: Brain, label: "Analyze" },
                { icon: Play, label: "Deploy" },
                { icon: Terminal, label: "Logs" },
              ].map((action) => (
                <button
                  key={action.label}
                  onClick={() => handleCardAction(action.label, repo)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-background-secondary border border-border/80 hover:bg-card-hover text-foreground-muted hover:text-foreground transition-colors cursor-pointer shadow-sm"
                >
                  <action.icon size={14} />
                  {action.label}
                </button>
              ))}
            </div>
          </motion.div>
        ))}
      </div>

      {/* Connect Repo Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-card max-w-md w-full p-6 rounded-xl border border-border shadow-2xl relative"
          >
            <button
              onClick={() => setIsModalOpen(false)}
              className="absolute top-4 right-4 text-foreground-muted hover:text-foreground cursor-pointer"
            >
              <X size={18} />
            </button>

            <h3 className="text-lg font-bold mb-2">Connect Repository</h3>
            <p className="text-xs text-foreground-muted mb-6">
              Connect a GitHub repository path to let ZeroOps configure and deploy it.
            </p>

            <form onSubmit={handleConnect} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-foreground-muted mb-1.5">Repository Path</label>
                <input
                  type="text"
                  value={repoName}
                  onChange={(e) => setRepoName(e.target.value)}
                  placeholder={`e.g. ${user?.github_username || "acme"}/billing-service`}
                  className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none placeholder:text-foreground-muted"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-foreground-muted mb-1.5">
                  Framework / Runtime
                </label>
                <select
                  value={framework}
                  onChange={(e) => setFramework(e.target.value)}
                  className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none cursor-pointer"
                >
                  <option value="Next.js">Next.js (TypeScript)</option>
                  <option value="Express.js">Express.js (TypeScript)</option>
                  <option value="FastAPI">FastAPI (Python)</option>
                  <option value="NestJS">NestJS (TypeScript)</option>
                  <option value="Flask">Flask (Python)</option>
                </select>
              </div>

              <div className="flex gap-3 justify-end pt-4">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 border border-border rounded-lg text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 bg-primary hover:bg-primary-hover disabled:opacity-50 text-white rounded-lg text-xs font-semibold transition glow-blue flex items-center gap-1.5 cursor-pointer"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 size={12} className="animate-spin" />
                      Connecting
                    </>
                  ) : (
                    "Connect"
                  )}
                </button>
              </div>
            </form>
          </motion.div>
        </div>
      )}
    </div>
  );
}


// GitHub Icon SVG component
function GithubIcon({ size = 18, className }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" className={className}>
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
}
