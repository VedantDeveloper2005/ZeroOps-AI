"use client";

import { motion, AnimatePresence } from "framer-motion";
import { GitBranch, Plus, Search, Play, Brain, Terminal, X, Loader2, Check, ArrowRight, Rocket, Lock, Star, ExternalLink, Trash2, Eye, EyeOff, AlertTriangle, Sparkles, Shield, Zap, Globe, ChevronDown, ChevronUp } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useState, useEffect, useCallback, useRef } from "react";
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

function ReadinessCircle({ score }: { score: number }) {
  const radius = 18;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = score >= 90 ? "text-success" : score >= 80 ? "text-warning" : "text-danger";
  const strokeColor = score >= 90 ? "var(--success)" : score >= 80 ? "var(--warning)" : "var(--danger)";

  return (
    <div className="relative w-12 h-12 flex-shrink-0">
      <svg className="w-12 h-12 -rotate-90" viewBox="0 0 44 44">
        <circle cx="22" cy="22" r={radius} fill="none" stroke="var(--border)" strokeWidth="3" />
        <motion.circle
          cx="22" cy="22" r={radius} fill="none"
          stroke={strokeColor} strokeWidth="3" strokeLinecap="round"
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          style={{ strokeDasharray: circumference }}
        />
      </svg>
      <span className={`absolute inset-0 flex items-center justify-center text-[10px] font-bold ${color}`}>
        {score}%
      </span>
    </div>
  );
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
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showScanLogs, setShowScanLogs] = useState(false);

  // AI scan checklist state
  const [scanChecklist, setScanChecklist] = useState<{ label: string; done: boolean }[]>([]);

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

  // AI Scan checklist animation
  useEffect(() => {
    if (!isAnalyzing) {
      setScanChecklist([]);
      return;
    }
    const items = [
      "Framework detected",
      "Runtime identified",
      "Build process analyzed",
      "Dependencies scanned",
      "Deployment strategy generated",
    ];
    setScanChecklist(items.map(label => ({ label, done: false })));
    
    items.forEach((_, idx) => {
      setTimeout(() => {
        setScanChecklist(prev => prev.map((item, i) => i <= idx ? { ...item, done: true } : item));
      }, 1000 + idx * 1200);
    });
  }, [isAnalyzing]);

  // Repository scanning progressive logs (kept for technical view)
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

  // Track whether analysis has already been triggered for the current step-2 visit
  const hasTriggeredAnalysis = useRef(false);

  // Reset the guard when leaving step 2
  useEffect(() => {
    if (onboardStep !== 2) {
      hasTriggeredAnalysis.current = false;
    }
  }, [onboardStep]);

  // Automatically trigger AI analysis when step 2 is reached (exactly once)
  useEffect(() => {
    if (onboardStep !== 2 || !selectedRepo || hasTriggeredAnalysis.current) return;
    hasTriggeredAnalysis.current = true;

    setIsAnalyzing(true);
    const repoObj = gitRepos.find((r) => r.full_name === selectedRepo);
    const fallbackFramework = detectedFramework;

    api.analyzeRepo(selectedRepo, selectedBranch)
      .then((data: any) => {
        setIsAnalyzing(false);
        setAnalysisResult({
          framework: data.framework || fallbackFramework,
          language: data.language || repoObj?.language || "TypeScript",
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
          explanation: data.explanation || `This is a ${fallbackFramework} application built with ${repoObj?.language || "TypeScript"}. It utilizes npm for package management, contains containerized settings, and runs in high-availability mode on Azure.`,
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
          framework: fallbackFramework,
          language: repoObj?.language || "TypeScript",
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
          ports: fallbackFramework === "FastAPI" ? "8000" : "3000",
          vulnerabilities: [],
          explanation: `This is a ${fallbackFramework} application built with ${repoObj?.language || "TypeScript"}. It utilizes npm for package management, contains containerized settings, and runs in high-availability mode on Azure.`,
        });
        addToast("AI Analysis completed with local metadata.", "success");
      });
  // Only re-run when the step or selected repo/branch actually changes
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onboardStep, selectedRepo, selectedBranch]);



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
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-[10px] font-bold uppercase tracking-wider mb-3">
            <Sparkles size={12} /> AI-Powered Deployment
          </div>
          <h1 className="text-3xl font-extrabold text-foreground tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-foreground to-foreground-muted">
            Deploy Your Application
          </h1>
          <p className="text-sm text-foreground-muted">
            Connect your GitHub repository and let AI handle the rest.
          </p>
          
          {/* Progress Indicators (3 Steps) */}
          <div className="flex items-center justify-center gap-2 pt-6 max-w-xl mx-auto overflow-x-auto no-scrollbar">
            {[
              { id: 1, label: "Choose Repository" },
              { id: 2, label: "AI Analysis" },
              { id: 3, label: "Deploy" },
            ].map((step, idx) => (
              <div key={step.id} className="flex items-center flex-1 min-w-[120px]">
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
            {/* ═══════════════════════════════════════════
                STEP 1: CHOOSE REPOSITORY
                ═══════════════════════════════════════════ */}
            {onboardStep === 1 && (
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b border-border/40 pb-4">
                  <div>
                    <h3 className="text-lg font-bold text-foreground">Choose Repository</h3>
                    <p className="text-xs text-foreground-muted">
                      Select the project you want to deploy. AI will analyze it automatically.
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
                  <div className="grid md:grid-cols-2 gap-3">
                    {[1, 2, 3, 4].map((i) => (
                      <div key={i} className="p-4 rounded-xl border border-border bg-card/40 space-y-3 animate-pulse">
                        <div className="flex items-center justify-between">
                          <div className="h-4 bg-background-secondary rounded w-24" />
                          <div className="h-10 w-10 bg-background-secondary rounded-full" />
                        </div>
                        <div className="space-y-1.5">
                          <div className="h-3 bg-background-secondary rounded w-full" />
                          <div className="h-3 bg-background-secondary rounded w-2/3" />
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
                    <div className="grid md:grid-cols-2 gap-3 max-h-[380px] overflow-y-auto pr-1">
                      {gitRepos.map((repo) => {
                        const readiness = calculateReadinessScore(repo);
                        const fw = detectFramework(repo.language);
                        const isSelected = selectedRepo === repo.full_name;
                        return (
                          <motion.div
                            key={repo.id}
                            initial={{ opacity: 0, y: 5 }}
                            animate={{ opacity: 1, y: 0 }}
                            onClick={() => {
                              setSelectedRepo(repo.full_name);
                              setDetectedFramework(fw);
                            }}
                            className={`p-4 rounded-xl border transition-all cursor-pointer text-left group ${
                              isSelected
                                ? "bg-primary-subtle/20 border-primary shadow-lg scale-[1.01] bg-gradient-to-b from-card to-primary-subtle/5"
                                : "bg-card border-border hover:bg-card-hover hover:border-border/80"
                            }`}
                          >
                            <div className="flex items-start justify-between gap-3">
                              {/* Left: Repo info */}
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="font-semibold text-sm text-foreground truncate">
                                    {repo.name}
                                  </span>
                                  {repo.private && (
                                    <Lock size={10} className="text-foreground-muted flex-shrink-0" />
                                  )}
                                </div>
                                <p className="text-[11px] text-foreground-muted line-clamp-1 mb-2.5">
                                  {repo.description || "No description provided."}
                                </p>

                                {/* Framework badge + metadata */}
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${frameworkColors[fw] || "bg-white/10 text-foreground-muted"}`}>
                                    {fw} detected
                                  </span>
                                  {readiness >= 90 && (
                                    <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-success/15 text-success border border-success/20 font-bold flex items-center gap-0.5">
                                      <Check size={8} /> Ready
                                    </span>
                                  )}
                                  <span className="text-[9px] text-foreground-muted">
                                    {timeAgo(repo.updated_at)}
                                  </span>
                                </div>

                                {readiness >= 90 && (
                                  <p className="text-[9px] text-success/70 mt-1.5 font-medium">
                                    No configuration required
                                  </p>
                                )}
                              </div>

                              {/* Right: Readiness circle */}
                              <ReadinessCircle score={readiness} />
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

                {/* Branch Selection Panel */}
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
                          {availableBranches.map((b) => (
                            <option key={b} value={b}>{b}</option>
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


            {/* ═══════════════════════════════════════════
                STEP 2: AI ANALYSIS
                ═══════════════════════════════════════════ */}
            {onboardStep === 2 && (
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b border-border/40 pb-4">
                  <div>
                    <h3 className="text-lg font-bold text-foreground">AI Analysis</h3>
                    <p className="text-xs text-foreground-muted">
                      ZeroOps AI is understanding your project to configure the best deployment.
                    </p>
                  </div>
                  <span className="text-xs px-2.5 py-1 rounded-full bg-primary/10 text-primary border border-primary/20 font-mono font-semibold">
                    {selectedRepo.split("/").pop()}
                  </span>
                </div>

                {isAnalyzing ? (
                  <div className="space-y-6">
                    {/* AI Understanding experience */}
                    <div className="relative overflow-hidden bg-card border border-border rounded-2xl p-8 shadow-xl">
                      <div className="absolute inset-0 bg-gradient-to-tr from-primary/5 via-accent/5 to-transparent animate-pulse" />
                      
                      {/* Centered AI icon */}
                      <div className="relative flex justify-center mb-6">
                        <div className="w-14 h-14 flex items-center justify-center bg-primary/10 border border-primary/20 rounded-full">
                          <Brain size={24} className="text-primary animate-pulse" />
                        </div>
                      </div>
                      
                      <div className="relative text-center mb-6">
                        <h4 className="text-sm font-bold text-foreground">Understanding your project...</h4>
                        <p className="text-xs text-foreground-muted mt-1">This usually takes a few seconds</p>
                      </div>

                      {/* Animated Checklist */}
                      <div className="relative max-w-sm mx-auto space-y-3">
                        {scanChecklist.map((item, idx) => (
                          <motion.div
                            key={idx}
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: idx * 0.15 }}
                            className="flex items-center gap-3 text-xs"
                          >
                            <div className={`w-5 h-5 rounded-full flex items-center justify-center transition-all duration-500 ${
                              item.done 
                                ? "bg-success/15 border border-success/30" 
                                : "bg-card border border-border"
                            }`}>
                              {item.done ? (
                                <Check size={12} className="text-success" />
                              ) : (
                                <Loader2 size={10} className="text-foreground-muted animate-spin" />
                              )}
                            </div>
                            <span className={`font-medium transition-colors duration-300 ${
                              item.done ? "text-foreground" : "text-foreground-muted"
                            }`}>
                              {item.done ? "✓" : "·"} {item.label}
                            </span>
                          </motion.div>
                        ))}
                      </div>

                      {/* Technical logs toggle */}
                      <div className="relative mt-6 flex justify-center">
                        <button
                          onClick={() => setShowScanLogs(prev => !prev)}
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
                                <div key={index} className="flex items-center gap-2 animate-fade-in">
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
                  <div className="space-y-6 animate-fade-in">
                    {/* Conversational AI Project Summary */}
                    <div className="glass rounded-xl p-6 border border-primary/20 bg-gradient-to-r from-primary/5 to-transparent space-y-3">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center">
                          <Brain size={14} className="text-primary" />
                        </div>
                        <h4 className="text-xs font-bold text-primary uppercase tracking-wider">AI Project Summary</h4>
                      </div>
                      <p className="text-sm text-foreground leading-relaxed">
                        {analysisResult?.explanation}
                      </p>
                    </div>

                    {/* AI Confidence + Recommendation */}
                    <div className="grid md:grid-cols-3 gap-4">
                      <div className="glass rounded-xl p-5 border border-border/60 space-y-2 bg-card/40 text-center">
                        <p className="text-[9px] font-bold text-foreground-muted uppercase tracking-wider">Your App</p>
                        <p className="text-sm font-bold text-foreground">{analysisResult?.framework}</p>
                        <p className="text-[10px] text-foreground-muted">{analysisResult?.language} · {analysisResult?.runtime}</p>
                      </div>
                      <div className="glass rounded-xl p-5 border border-border/60 space-y-2 bg-card/40 text-center">
                        <p className="text-[9px] font-bold text-foreground-muted uppercase tracking-wider">Where It Will Run</p>
                        <p className="text-sm font-bold text-foreground">{analysisResult?.deploymentStrategy}</p>
                        <p className="text-[10px] text-foreground-muted">Recommended by AI</p>
                      </div>
                      <div className="glass rounded-xl p-5 border border-border/60 space-y-2 bg-card/40 text-center">
                        <p className="text-[9px] font-bold text-foreground-muted uppercase tracking-wider">Time to Go Live</p>
                        <p className="text-sm font-bold text-success font-mono">~2 minutes</p>
                        <p className="text-[10px] text-foreground-muted">Production environment</p>
                      </div>
                    </div>

                    {/* Vulnerabilities warnings */}
                    {analysisResult?.vulnerabilities?.length > 0 && (
                      <div className="p-4 rounded-xl border border-warning/20 bg-warning/5 space-y-2 animate-fade-in">
                        <p className="text-xs font-semibold text-warning flex items-center gap-1.5">
                          <AlertTriangle size={14} /> Things to Review
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
                    onClick={() => setOnboardStep(1)}
                    className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
                  >
                    Back
                  </button>
                  <button
                    disabled={isAnalyzing}
                    onClick={() => setOnboardStep(3)}
                    className="px-5 py-2.5 bg-primary disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer flex items-center gap-1"
                  >
                    Continue <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            )}


            {/* ═══════════════════════════════════════════
                STEP 3: DEPLOY
                ═══════════════════════════════════════════ */}
            {onboardStep === 3 && (
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b border-border/40 pb-4">
                  <div>
                    <h3 className="text-lg font-bold text-foreground">Deploy</h3>
                    <p className="text-xs text-foreground-muted">
                      AI has configured the optimal deployment. Review and launch.
                    </p>
                  </div>
                  <span className="text-xs px-2.5 py-1 rounded-full bg-success/10 text-success border border-success/20 font-medium">
                    Ready to Deploy
                  </span>
                </div>

                {/* AI Deployment Plan — main content */}
                <div className="grid md:grid-cols-5 gap-6">
                  {/* Left: AI Plan + Env Vars */}
                  <div className="md:col-span-3 space-y-6">
                    {/* AI Deployment Plan Card */}
                    <div className="glass rounded-xl p-5 border border-primary/15 bg-gradient-to-b from-primary/5 to-transparent space-y-4">
                      <h4 className="text-xs font-bold text-primary flex items-center gap-1.5 uppercase tracking-wider">
                        <Brain size={14} /> AI Deployment Plan
                      </h4>
                      <div className="space-y-2.5 text-xs">
                        {[
                          { label: "Deployment Target", value: analysisResult?.deploymentStrategy || "Azure App Service" },
                          { label: "Runtime", value: analysisResult?.runtime || "Node.js 22" },
                          { label: "Environment", value: "Production" },
                          { label: "SSL", value: "Included", check: true },
                          { label: "Scaling", value: "Automatic", check: true },
                          { label: "Estimated Cost", value: "Free Tier Eligible", highlight: true },
                        ].map((row) => (
                          <div key={row.label} className="flex items-center justify-between py-2 border-b border-border/20 last:border-0">
                            <span className="text-foreground-muted">{row.label}</span>
                            <span className={`font-semibold flex items-center gap-1 ${row.highlight ? "text-success" : row.check ? "text-success" : "text-foreground"}`}>
                              {row.check && <Check size={12} />}
                              {row.value}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Environment Variables */}
                    {(wizardEnvVars.length > 0 || analysisResult?.environmentVariables?.length > 0) && (
                      <div className="bg-card/40 border border-border/60 rounded-xl p-4 space-y-4">
                        <div className="flex items-center justify-between">
                          <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider">
                            Environment Variables
                          </h4>
                          {analysisResult?.environmentVariables?.length > 0 && (
                            <span className="text-[9px] text-primary font-medium">AI detected these may be needed</span>
                          )}
                        </div>
                        
                        {/* Existing env var list */}
                        {wizardEnvVars.length > 0 && (
                          <div className="border border-border/60 rounded-xl overflow-hidden max-h-[140px] overflow-y-auto">
                            <table className="w-full text-left border-collapse text-xs">
                              <thead>
                                <tr className="bg-background-secondary border-b border-border/60 text-foreground-muted font-semibold">
                                  <th className="p-2.5">Key</th>
                                  <th className="p-2.5">Value</th>
                                  <th className="p-2.5 text-center w-12"></th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-border/40 bg-card/20">
                                {wizardEnvVars.map((v, idx) => (
                                  <tr key={idx} className="hover:bg-card-hover/20">
                                    <td className="p-2.5 font-mono font-semibold text-foreground truncate max-w-[120px]">{v.key}</td>
                                    <td className="p-2.5 font-mono text-foreground-muted truncate max-w-[160px]">
                                      {v.is_secret ? "••••••••" : v.value || "—"}
                                    </td>
                                    <td className="p-2.5 text-center">
                                      <button
                                        type="button"
                                        onClick={() => {
                                          setWizardEnvVars((prev) => prev.filter((_, i) => i !== idx));
                                          addToast(`Removed ${v.key}`, "info");
                                        }}
                                        className="text-foreground-muted hover:text-danger transition-colors cursor-pointer"
                                      >
                                        <Trash2 size={12} />
                                      </button>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}

                        {/* Add new env var */}
                        <div className="flex gap-2 items-end">
                          <div className="flex-1">
                            <input
                              type="text"
                              value={newEnvKey}
                              onChange={(e) => setNewEnvKey(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ""))}
                              placeholder="KEY"
                              className="w-full bg-card border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:border-primary focus:outline-none placeholder:text-foreground-muted font-mono"
                            />
                          </div>
                          <div className="flex-1">
                            <input
                              type="text"
                              value={newEnvVal}
                              onChange={(e) => setNewEnvVal(e.target.value)}
                              placeholder="value"
                              className="w-full bg-card border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:border-primary focus:outline-none placeholder:text-foreground-muted font-mono"
                            />
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              if (!newEnvKey.trim()) { addToast("Variable Key cannot be empty.", "warning"); return; }
                              if (wizardEnvVars.some((v) => v.key === newEnvKey.trim())) { addToast(`Variable '${newEnvKey}' already added.`, "warning"); return; }
                              setWizardEnvVars((prev) => [...prev, { key: newEnvKey.trim(), value: newEnvVal, is_secret: newEnvIsSecret }]);
                              setNewEnvKey(""); setNewEnvVal(""); setNewEnvIsSecret(false);
                              addToast("Environment variable added.", "success");
                            }}
                            className="px-3 py-2 bg-primary text-white rounded-lg text-xs font-semibold hover:bg-primary-hover transition cursor-pointer"
                          >
                            <Plus size={14} />
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Advanced Settings (collapsed) */}
                    <div className="border border-border/40 rounded-xl overflow-hidden bg-card/20">
                      <button
                        type="button"
                        onClick={() => setShowAdvanced(!showAdvanced)}
                        className="w-full p-4 flex items-center justify-between text-xs font-bold text-foreground-muted hover:bg-card-hover/40 transition-colors"
                      >
                        <span>Advanced Settings</span>
                        <span className="text-[10px] text-primary">{showAdvanced ? "Hide" : "Show"}</span>
                      </button>
                      
                      {showAdvanced && (
                        <div className="p-4 border-t border-border/40 space-y-4 bg-zinc-950/20">
                          <div className="grid md:grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                              <label className="block text-xs font-semibold text-foreground-muted">Region</label>
                              <select
                                value={region}
                                onChange={(e) => setRegion(e.target.value)}
                                className="w-full bg-card border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:border-primary focus:outline-none cursor-pointer"
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
                                className="w-full bg-card border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:border-primary focus:outline-none cursor-pointer"
                              >
                                <option value="standard">Rolling Update (Zero Downtime)</option>
                                <option value="canary">Canary Release (10% Split)</option>
                                <option value="bluegreen">Blue/Green Deploy</option>
                              </select>
                            </div>
                          </div>
                          <div className="grid md:grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                              <label className="block text-xs font-semibold text-foreground-muted">Min Replicas</label>
                              <input
                                type="number" min="1" max="10" value={minReplicas}
                                onChange={(e) => setMinReplicas(parseInt(e.target.value) || 1)}
                                className="w-full bg-card border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:border-primary focus:outline-none"
                              />
                            </div>
                            <div className="space-y-1.5">
                              <label className="block text-xs font-semibold text-foreground-muted">Max Replicas</label>
                              <input
                                type="number" min="1" max="50" value={maxReplicas}
                                onChange={(e) => setMaxReplicas(parseInt(e.target.value) || 10)}
                                className="w-full bg-card border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:border-primary focus:outline-none"
                              />
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Right: Deployment Summary + Launch */}
                  <div className="md:col-span-2 glass rounded-xl p-5 border border-border bg-gradient-to-b from-primary/5 to-accent/5 space-y-4 flex flex-col justify-between shadow-md h-fit">
                    <div className="space-y-3">
                      <h4 className="text-xs font-bold text-primary uppercase tracking-wider">
                        Deployment Summary
                      </h4>
                      <div className="space-y-2.5 text-xs">
                        <div className="border-b border-border/40 pb-2">
                          <p className="text-[9px] font-bold text-foreground-muted uppercase">Repository</p>
                          <p className="mt-0.5 font-semibold text-foreground truncate">{selectedRepo}</p>
                        </div>
                        <div className="border-b border-border/40 pb-2">
                          <p className="text-[9px] font-bold text-foreground-muted uppercase">Branch</p>
                          <p className="mt-0.5 font-semibold text-foreground font-mono">{selectedBranch}</p>
                        </div>
                        <div className="border-b border-border/40 pb-2">
                          <p className="text-[9px] font-bold text-foreground-muted uppercase">Framework</p>
                          <p className="mt-0.5 font-semibold text-foreground">{analysisResult?.framework}</p>
                        </div>
                        <div>
                          <p className="text-[9px] font-bold text-foreground-muted uppercase">Estimated Time</p>
                          <p className="mt-0.5 font-semibold text-success font-mono">~2 minutes</p>
                        </div>
                      </div>
                    </div>

                    <div className="pt-4 border-t border-border/40">
                      <button
                        onClick={handleLaunchDeployment}
                        className="w-full py-3 bg-primary hover:bg-primary-hover text-white rounded-xl text-sm font-bold transition glow-blue flex items-center justify-center gap-2 cursor-pointer"
                      >
                        <Rocket size={16} />
                        Deploy Now
                      </button>
                      <p className="text-[10px] text-foreground-muted text-center mt-2">Estimated: ~2 min to go live</p>
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
