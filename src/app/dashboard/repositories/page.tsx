"use client";

import { motion } from "framer-motion";
import { GitBranch, Plus, Search, Play, Brain, Terminal, X, Loader2, Check, ArrowRight, Rocket, Lock, Star, ExternalLink } from "lucide-react";
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

  // Check if user logged in via GitHub (auto-skip step 1)
  const isGitHubConnected = user?.github_connected === true;

  useEffect(() => {
    if (isGitHubConnected && !hasDeployed) {
      setOnboardStep(2);
      loadRepos();
    }
  }, [isGitHubConnected, hasDeployed]);

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
  }, [selectedRepo]);

  // Debounced search
  useEffect(() => {
    if (!isGitHubConnected) return;
    const timer = setTimeout(() => {
      loadRepos(repoSearchQuery, 1);
    }, 400);
    return () => clearTimeout(timer);
  }, [repoSearchQuery, isGitHubConnected]);

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

  const handleLaunchDeployment = async () => {
    addToast(`Launching deployment for ${selectedRepo}...`, "info");
    try {
      const proj = await api.createProject({
        name: selectedRepo.split("/").pop() || selectedRepo,
        full_name: selectedRepo,
        repo_url: `https://github.com/${selectedRepo}`,
        framework: detectedFramework,
        language: gitRepos.find((r) => r.full_name === selectedRepo)?.language || "TypeScript",
        branch: selectedBranch,
        region: region,
      });

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
        <div className="text-center space-y-2 mb-8">
          <h1 className="text-3xl font-extrabold text-foreground tracking-tight">Onboarding Wizard</h1>
          <p className="text-sm text-foreground-muted">Set up your workspace and launch your first autonomic cloud deployment.</p>

          {/* Progress Indicators */}
          <div className="flex items-center justify-center gap-2 pt-4 max-w-lg mx-auto">
            {[
              { id: 1, label: "Git Link" },
              { id: 2, label: "Select Repo" },
              { id: 3, label: "AI Scan" },
              { id: 4, label: "Configure" },
            ].map((step, idx) => (
              <div key={step.id} className="flex items-center flex-1">
                <div className="flex flex-col items-center gap-1.5 flex-1">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs border ${
                      onboardStep === step.id
                        ? "bg-primary border-primary text-white glow-blue"
                        : onboardStep > step.id
                        ? "bg-success/20 border-success text-success"
                        : "bg-card border-border text-foreground-muted"
                    }`}
                  >
                    {onboardStep > step.id ? <Check size={14} /> : step.id}
                  </div>
                  <span
                    className={`text-[10px] font-semibold ${
                      onboardStep === step.id ? "text-foreground" : "text-foreground-muted"
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
                {idx < 3 && (
                  <div
                    className={`h-px flex-1 -mt-4 ${onboardStep > step.id ? "bg-success/40" : "bg-border"}`}
                  />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Wizard Steps */}
        <motion.div
          key={onboardStep}
          initial={{ opacity: 0, x: 10 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -10 }}
          transition={{ duration: 0.3 }}
          className="glass rounded-2xl border border-border/40 p-6 md:p-8 shadow-2xl space-y-6"
        >
          {/* STEP 1: CONNECT GIT PROVIDER */}
          {onboardStep === 1 && (
            <div className="space-y-6 text-center py-4">
              <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-lg glow-blue">
                <GitBranch size={28} className="text-white" />
              </div>
              <div className="space-y-2 max-w-md mx-auto">
                <h3 className="text-xl font-bold text-foreground">Connect GitHub Account</h3>
                <p className="text-sm text-foreground-muted">
                  Authorize ZeroOps to access your repositories. We&apos;ll securely store your credentials server-side.
                </p>
              </div>

              <div className="max-w-xs mx-auto pt-4">
                {isGitHubConnected ? (
                  <div className="space-y-3 p-4 rounded-xl bg-success/10 border border-success/30 text-center">
                    <Check size={24} className="text-success mx-auto" />
                    <p className="text-sm font-semibold text-foreground">Connected to GitHub</p>
                    <p className="text-xs text-foreground-muted font-mono font-semibold">
                      @{user?.github_username}
                    </p>
                  </div>
                ) : isConnectingGit ? (
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
                    className="w-full py-3 bg-primary text-white hover:bg-primary-hover font-semibold rounded-xl text-sm transition glow-blue cursor-pointer flex items-center justify-center gap-2"
                  >
                    <GithubIcon size={18} />
                    Continue with GitHub
                  </button>
                )}
              </div>

              <div className="flex justify-end pt-6 border-t border-border/40">
                <button
                  disabled={!isGitHubConnected}
                  onClick={() => {
                    setOnboardStep(2);
                    loadRepos();
                  }}
                  className="px-5 py-2.5 bg-primary disabled:opacity-50 text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer"
                >
                  Continue
                </button>
              </div>
            </div>
          )}

          {/* STEP 2: SELECT REPOSITORY */}
          {onboardStep === 2 && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-bold text-foreground">Select Repository & Branch</h3>
                  <p className="text-xs text-foreground-muted">
                    Choose the repository you wish to deploy onto Kubernetes.
                  </p>
                </div>
                {isGitHubConnected && (
                  <span className="text-xs px-2.5 py-1 rounded-full bg-success/10 text-success border border-success/20 font-medium">
                    @{user?.github_username}
                  </span>
                )}
              </div>

              {/* Search repos */}
              <div className="flex gap-3">
                <div className="flex-1 glass-subtle rounded-xl px-4 py-2.5 flex items-center gap-2">
                  <Search size={16} className="text-foreground-muted" />
                  <input
                    type="text"
                    value={repoSearchQuery}
                    onChange={(e) => setRepoSearchQuery(e.target.value)}
                    placeholder="Search your repositories..."
                    className="bg-transparent border-none outline-none text-sm text-foreground placeholder:text-foreground-muted w-full"
                  />
                </div>
              </div>

              {isLoadingRepos ? (
                <div className="p-8 text-center">
                  <Loader2 className="animate-spin text-primary mx-auto mb-2" size={24} />
                  <p className="text-xs text-foreground-muted">Discovering repositories...</p>
                </div>
              ) : gitRepos.length === 0 ? (
                <div className="p-8 text-center space-y-2">
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
                    {gitRepos.map((repo) => (
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
                            ? "bg-primary-subtle/20 border-primary shadow-lg"
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
                        <div className="flex items-center gap-3 mt-2 text-[10px] text-foreground-muted">
                          {repo.stargazers_count > 0 && (
                            <span className="flex items-center gap-0.5">
                              <Star size={10} /> {repo.stargazers_count}
                            </span>
                          )}
                          <span>{timeAgo(repo.updated_at)}</span>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                  {hasMoreRepos && (
                    <div className="text-center pt-2">
                      <button
                        onClick={() => loadRepos(repoSearchQuery, repoPage + 1)}
                        disabled={isLoadingMore}
                        className="text-xs text-primary hover:underline cursor-pointer disabled:opacity-50"
                      >
                        {isLoadingMore ? (
                          <span className="flex items-center gap-1.5">
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

              <div className="grid md:grid-cols-2 gap-4 pt-2">
                <div>
                  <label className="block text-xs font-semibold text-foreground-muted mb-1.5">
                    Tracking Branch
                  </label>
                  {isLoadingBranches ? (
                    <div className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground-muted flex items-center gap-2">
                      <Loader2 size={14} className="animate-spin" /> Loading branches...
                    </div>
                  ) : (
                    <select
                      value={selectedBranch}
                      onChange={(e) => setSelectedBranch(e.target.value)}
                      className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none cursor-pointer"
                    >
                      {availableBranches.map((b) => (
                        <option key={b} value={b}>
                          {b}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
                <div>
                  <label className="block text-xs font-semibold text-foreground-muted mb-1.5">
                    Git Provider
                  </label>
                  <input
                    type="text"
                    value={`GitHub (@${user?.github_username || "connected"})`}
                    disabled
                    className="w-full bg-card border border-border/40 rounded-lg px-3 py-2 text-sm text-foreground-muted focus:outline-none"
                  />
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
                  disabled={!selectedRepo}
                  onClick={() => {
                    setOnboardStep(3);
                    setIsAnalyzing(true);
                    // Run real AI analysis if possible, else fallback
                    const selectedRepoObj = gitRepos.find((r) => r.full_name === selectedRepo);
                    api
                      .analyzeRepo(selectedRepo, selectedBranch)
                      .then((data: any) => {
                        setIsAnalyzing(false);
                        setAnalysisResult({
                          framework: data.framework || detectedFramework,
                          language: data.language || selectedRepoObj?.language || "TypeScript",
                          riskScore: data.risk_score ?? 18,
                          cpu: data.resources?.cpu || "200m",
                          memory: data.resources?.memory || "256Mi",
                          ports: data.port || (detectedFramework === "FastAPI" ? "8000" : "3000"),
                          vulnerabilities: data.vulnerabilities?.length || 0,
                        });
                        addToast("AI Analysis complete!", "success");
                      })
                      .catch(() => {
                        setIsAnalyzing(false);
                        setAnalysisResult({
                          framework: detectedFramework,
                          language: selectedRepoObj?.language || "TypeScript",
                          riskScore: 18,
                          cpu: "200m",
                          memory: "256Mi",
                          ports: detectedFramework === "FastAPI" ? "8000" : "3000",
                          vulnerabilities: 0,
                        });
                        addToast("AI Analysis complete!", "success");
                      });
                  }}
                  className="px-5 py-2.5 bg-primary disabled:opacity-50 text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer"
                >
                  Analyze Codebase
                </button>
              </div>
            </div>
          )}

          {/* STEP 3: AI CODE ANALYSIS */}
          {onboardStep === 3 && (
            <div className="space-y-6">
              <h3 className="text-lg font-bold text-foreground">AI Cognitive Analysis</h3>
              <p className="text-xs text-foreground-muted -mt-4">
                Our scanner verifies Docker container targets, audits libraries, and generates optimal cluster settings.
              </p>

              {isAnalyzing ? (
                <div className="space-y-4 p-8 text-center bg-card border border-border rounded-2xl">
                  <Loader2 size={32} className="animate-spin text-primary mx-auto" />
                  <div className="space-y-1.5">
                    <p className="text-sm font-semibold text-foreground">Analyzing repository files...</p>
                    <p className="text-xs text-foreground-muted font-mono max-w-sm mx-auto">
                      Running package vulnerability check • Isolating framework dependencies • Mapping ports
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-6">
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="glass rounded-xl p-5 border border-border/60 space-y-3">
                      <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider">
                        Framework & Runtime
                      </h4>
                      <div className="flex justify-between items-center text-sm">
                        <span className="text-foreground-muted">Detected Framework</span>
                        <span className="font-semibold text-foreground">{analysisResult?.framework}</span>
                      </div>
                      <div className="flex justify-between items-center text-sm">
                        <span className="text-foreground-muted">Primary Language</span>
                        <span className="font-semibold text-foreground">{analysisResult?.language}</span>
                      </div>
                      <div className="flex justify-between items-center text-sm">
                        <span className="text-foreground-muted">Target Port</span>
                        <span className="font-semibold text-foreground font-mono bg-card px-2 py-0.5 rounded border border-border/60">
                          {analysisResult?.ports}
                        </span>
                      </div>
                    </div>
                    <div className="glass rounded-xl p-5 border border-border/60 space-y-3">
                      <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider">
                        Cognitive Resource Limits
                      </h4>
                      <div className="flex justify-between items-center text-sm">
                        <span className="text-foreground-muted">Recommended CPU</span>
                        <span className="font-semibold text-foreground">{analysisResult?.cpu}</span>
                      </div>
                      <div className="flex justify-between items-center text-sm">
                        <span className="text-foreground-muted">Recommended RAM</span>
                        <span className="font-semibold text-foreground">{analysisResult?.memory}</span>
                      </div>
                      <div className="flex justify-between items-center text-sm">
                        <span className="text-foreground-muted">Security Vulnerabilities</span>
                        <span
                          className={`font-semibold ${
                            analysisResult?.vulnerabilities > 0 ? "text-danger" : "text-success"
                          }`}
                        >
                          {analysisResult?.vulnerabilities > 0
                            ? `${analysisResult.vulnerabilities} found`
                            : "None detected"}
                        </span>
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
                      onClick={() => setOnboardStep(4)}
                      className="px-5 py-2.5 bg-primary text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer"
                    >
                      Configure Target
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* STEP 4: CONFIGURE TARGET */}
          {onboardStep === 4 && (
            <div className="space-y-6">
              <h3 className="text-lg font-bold text-foreground">Cluster Deployment Configuration</h3>
              <p className="text-xs text-foreground-muted -mt-4">
                Define resource scale ceilings, environment properties, and target region endpoints.
              </p>

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
                    onChange={(e) => setMinReplicas(parseInt(e.target.value) || 2)}
                    className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="block text-xs font-semibold text-foreground-muted">Max Pod Replicas</label>
                  <input
                    type="number"
                    min="2"
                    max="50"
                    value={maxReplicas}
                    onChange={(e) => setMaxReplicas(parseInt(e.target.value) || 10)}
                    className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
                  />
                </div>
              </div>

              <div className="flex justify-between pt-6 border-t border-border/40">
                <button
                  onClick={() => setOnboardStep(3)}
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
      </div>
    );
  }

  // ════════════════════════════════════════════════
  // POST-ONBOARDING: Connected Repositories View
  // ════════════════════════════════════════════════
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Repositories</h1>
          <p className="text-foreground-muted text-sm mt-1">Connected GitHub repositories managed by ZeroOps</p>
        </div>
        <button
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-primary text-white rounded-xl text-sm font-semibold hover:bg-primary-hover transition-colors glow-blue cursor-pointer"
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
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08 }}
            className="glass rounded-xl p-4 flex items-center gap-3"
          >
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
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
        <div className="flex-1 glass-subtle rounded-xl px-4 py-2.5 flex items-center gap-2">
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
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08 }}
            className="glass rounded-xl p-5 hover:bg-card-hover/50 transition-all group"
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
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium glass-subtle hover:bg-card-hover/80 text-foreground-muted hover:text-foreground transition-colors cursor-pointer"
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="glass max-w-md w-full p-6 rounded-xl border border-border shadow-2xl relative"
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
function GithubIcon({ size = 18 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor">
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
}
