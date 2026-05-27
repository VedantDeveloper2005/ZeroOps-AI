"use client";

import { motion } from "framer-motion";
import { GitBranch, Plus, Search, Play, Brain, Terminal, X, Loader2, Check, ArrowRight, Rocket } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useState } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { useRouter } from "next/navigation";
import { createFallbackAnalysis } from "@/lib/demo-runtime";

const frameworkColors: Record<string, string> = {
  "Next.js": "bg-white/10 text-white",
  "Express.js": "bg-green-500/10 text-green-400",
  FastAPI: "bg-teal-500/10 text-teal-400",
  NestJS: "bg-red-500/10 text-red-400",
  Flask: "bg-blue-500/10 text-blue-400",
};
const langColors: Record<string, string> = { TypeScript: "bg-blue-500", Python: "bg-yellow-500" };

const frameworkToLanguage: Record<string, string> = {
  "Next.js": "TypeScript",
  "Express.js": "TypeScript",
  FastAPI: "Python",
  NestJS: "TypeScript",
  Flask: "Python",
};

export default function RepositoriesPage() {
  const router = useRouter();
  const { repositories, addRepository, addToast, addNotification, hasDeployed } = useNotifications();
  
  // Onboarding Wizard local states
  const [onboardStep, setOnboardStep] = useState(1);
  const [isConnectingGit, setIsConnectingGit] = useState(false);
  const [isGitConnected, setIsGitConnected] = useState(false);
  const [selectedRepo, setSelectedRepo] = useState("acme/web-app");
  const [selectedBranch, setSelectedBranch] = useState("main");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  
  // Deployment config states
  const [envVars, setEnvVars] = useState([{ key: "NODE_ENV", value: "production" }]);
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
  const [branchesByRepo, setBranchesByRepo] = useState<Record<string, string[]>>({});

  const filtered = repositories.filter(r => r.name.toLowerCase().includes(search.toLowerCase()) || r.fullName.toLowerCase().includes(search.toLowerCase()));

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
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs border ${
                    onboardStep === step.id 
                      ? "bg-primary border-primary text-white glow-blue" 
                      : onboardStep > step.id 
                      ? "bg-success/20 border-success text-success" 
                      : "bg-card border-border text-foreground-muted"
                  }`}>
                    {step.id}
                  </div>
                  <span className={`text-[10px] font-semibold ${onboardStep === step.id ? "text-foreground" : "text-foreground-muted"}`}>
                    {step.label}
                  </span>
                </div>
                {idx < 3 && (
                  <div className={`h-px flex-1 -mt-4 ${onboardStep > step.id ? "bg-success/40" : "bg-border"}`} />
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
                <h3 className="text-xl font-bold text-foreground">Connect Git Account</h3>
                <p className="text-sm text-foreground-muted">Link your GitHub organization or personal repository namespace so ZeroOps can capture webhooks and build source code.</p>
              </div>

              <div className="max-w-xs mx-auto pt-4">
                {isConnectingGit ? (
                  <div className="space-y-3 p-4 rounded-xl bg-card border border-border text-center">
                    <Loader2 size={24} className="animate-spin text-primary mx-auto" />
                    <p className="text-xs font-mono text-foreground-muted">Generating secure oauth token...</p>
                  </div>
                ) : isGitConnected ? (
                  <div className="space-y-3 p-4 rounded-xl bg-success/10 border border-success/30 text-center">
                    <Check size={24} className="text-success mx-auto" />
                    <p className="text-sm font-semibold text-foreground">Connected to GitHub</p>
                    <p className="text-xs text-foreground-muted font-mono font-semibold">github.com/vedantdeveloper2005</p>
                  </div>
                ) : (
                  <button
                    onClick={() => {
                      setIsConnectingGit(true);
                      setTimeout(() => {
                        setIsConnectingGit(false);
                        setIsGitConnected(true);
                        addToast("Successfully linked GitHub account!", "success");
                      }, 1800);
                    }}
                    className="w-full py-3 bg-primary text-white hover:bg-primary-hover font-semibold rounded-xl text-sm transition glow-blue cursor-pointer"
                  >
                    Link GitHub Account
                  </button>
                )}
              </div>

              <div className="flex justify-end pt-6 border-t border-border/40">
                <button
                  disabled={!isGitConnected}
                  onClick={() => setOnboardStep(2)}
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
              <h3 className="text-lg font-bold text-foreground">Select Repository & Branch</h3>
              <p className="text-xs text-foreground-muted -mt-4">Choose the repository and tracking branch you wish to deploy onto Kubernetes.</p>
              
              <div className="grid md:grid-cols-3 gap-4">
                {[
                  { name: "acme/web-app", desc: "Next.js storefront dashboard frontend", framework: "Next.js" },
                  { name: "acme/api-gateway", desc: "Express.js API ingestion gateway", framework: "Express.js" },
                  { name: "acme/payments-service", desc: "FastAPI payment processing gateway", framework: "FastAPI" },
                ].map((repo) => (
                  <div
                    key={repo.name}
                    onClick={() => {
                      setSelectedRepo(repo.name);
                      setDetectedFramework(repo.framework);
                    }}
                    className={`p-4 rounded-xl border transition-all cursor-pointer text-left ${
                      selectedRepo === repo.name
                        ? "bg-primary-subtle/20 border-primary shadow-lg"
                        : "bg-card border-border hover:bg-card-hover"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5 flex-wrap gap-2">
                      <span className="font-semibold text-xs text-foreground truncate max-w-[130px]">{repo.name}</span>
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/10 text-white font-medium">{repo.framework}</span>
                    </div>
                    <p className="text-[11px] text-foreground-muted">{repo.desc}</p>
                  </div>
                ))}
              </div>

              <div className="grid md:grid-cols-2 gap-4 pt-2">
                <div>
                  <label className="block text-xs font-semibold text-foreground-muted mb-1.5">Tracking Branch</label>
                  <select
                    value={selectedBranch}
                    onChange={(e) => setSelectedBranch(e.target.value)}
                    className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none cursor-pointer"
                  >
                    <option value="main">main</option>
                    <option value="develop">develop</option>
                    <option value="staging">staging</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-foreground-muted mb-1.5">Git Provider</label>
                  <input
                    type="text"
                    value="GitHub (Connected)"
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
                  onClick={() => {
                    setOnboardStep(3);
                    setIsAnalyzing(true);
                    setTimeout(() => {
                      setIsAnalyzing(false);
                      setAnalysisResult({
                        framework: detectedFramework,
                        language: detectedFramework === "FastAPI" ? "Python" : "TypeScript",
                        riskScore: 18,
                        cpu: "200m",
                        memory: "256Mi",
                        ports: detectedFramework === "Next.js" ? "3000" : detectedFramework === "FastAPI" ? "8000" : "5000",
                      });
                      addToast("AI Analysis complete!", "success");
                    }, 2200);
                  }}
                  className="px-5 py-2.5 bg-primary text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer"
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
              <p className="text-xs text-foreground-muted -mt-4">Our scanner verifies Docker container targets, audits libraries, and generates optimal cluster settings.</p>

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
                  {/* Analysis output */}
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="glass rounded-xl p-5 border border-border/60 space-y-3">
                      <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider">Framework & Runtime</h4>
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
                        <span className="font-semibold text-foreground font-mono bg-card px-2 py-0.5 rounded border border-border/60">{analysisResult?.ports}</span>
                      </div>
                    </div>

                    <div className="glass rounded-xl p-5 border border-border/60 space-y-3">
                      <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider">Cognitive Resource Limits</h4>
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
                        <span className="font-semibold text-success">None detected</span>
                      </div>
                    </div>
                  </div>

                  <div className="p-4 rounded-xl bg-card border border-border/60 space-y-2">
                    <span className="text-xs font-bold text-accent">AI SUGGESTION</span>
                    <p className="text-xs text-foreground-muted leading-relaxed">
                      "ZeroOps AI detected {analysisResult?.framework} architecture. We generated an optimized Alpine-based Dockerfile and a rolling-update deployment Kubernetes manifest target. The risk profile is low (Score: {analysisResult?.riskScore})."
                    </p>
                  </div>
                </div>
              )}

              <div className="flex justify-between pt-6 border-t border-border/40">
                <button
                  disabled={isAnalyzing}
                  onClick={() => setOnboardStep(2)}
                  className="px-4 py-2 border border-border rounded-xl text-xs font-semibold hover:bg-card-hover transition cursor-pointer"
                >
                  Back
                </button>
                <button
                  disabled={isAnalyzing}
                  onClick={() => setOnboardStep(4)}
                  className="px-5 py-2.5 bg-primary text-white rounded-xl text-xs font-semibold hover:bg-primary-hover transition cursor-pointer"
                >
                  Configure Deployment
                </button>
              </div>
            </div>
          )}

          {/* STEP 4: CONFIGURE DEPLOYMENT */}
          {onboardStep === 4 && (
            <div className="space-y-6">
              <h3 className="text-lg font-bold text-foreground">Configure Deployment Options</h3>
              <p className="text-xs text-foreground-muted -mt-4">Fine-tune environment variables, datacenter hosting zones, and autoscaling thresholds before going live.</p>

              <div className="grid md:grid-cols-2 gap-6">
                {/* Left col - env vars */}
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <span className="text-xs font-bold text-foreground-muted uppercase tracking-wider">Environment Variables</span>
                    <button
                      type="button"
                      onClick={() => setEnvVars([...envVars, { key: "", value: "" }])}
                      className="text-xs text-primary font-semibold hover:underline"
                    >
                      + Add row
                    </button>
                  </div>
                  
                  <div className="space-y-2 max-h-[160px] overflow-y-auto pr-1 no-scrollbar">
                    {envVars.map((v, idx) => (
                      <div key={idx} className="flex gap-2 items-center">
                        <input
                          type="text"
                          value={v.key}
                          onChange={(e) => {
                            const next = [...envVars];
                            next[idx].key = e.target.value;
                            setEnvVars(next);
                          }}
                          placeholder="KEY"
                          className="flex-1 bg-card border border-border rounded-lg px-2.5 py-1.5 text-xs font-mono text-foreground focus:outline-none focus:border-primary"
                        />
                        <span className="text-foreground-muted text-xs">=</span>
                        <input
                          type="text"
                          value={v.value}
                          onChange={(e) => {
                            const next = [...envVars];
                            next[idx].value = e.target.value;
                            setEnvVars(next);
                          }}
                          placeholder="VALUE"
                          className="flex-1 bg-card border border-border rounded-lg px-2.5 py-1.5 text-xs font-mono text-foreground focus:outline-none focus:border-primary"
                        />
                        <button
                          type="button"
                          onClick={() => setEnvVars(envVars.filter((_, i) => i !== idx))}
                          className="text-danger hover:text-danger-hover text-xs font-semibold px-1"
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Right col - hosting/scaling */}
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-bold text-foreground-muted uppercase tracking-wider mb-1.5">Hosting Region</label>
                    <select
                      value={region}
                      onChange={(e) => setRegion(e.target.value)}
                      className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none cursor-pointer"
                    >
                      <option value="eastus">East US (Recommended)</option>
                      <option value="westus2">West US 2</option>
                      <option value="northeurope">North Europe</option>
                      <option value="eastasia">East Asia</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-foreground-muted uppercase tracking-wider mb-1.5">Autoscaling Limits</label>
                    <div className="flex gap-4 items-center">
                      <div className="flex-1">
                        <label className="block text-[10px] text-foreground-muted mb-1">Min Replicas</label>
                        <input
                          type="number"
                          value={minReplicas}
                          onChange={(e) => setMinReplicas(parseInt(e.target.value))}
                          className="w-full bg-card border border-border rounded-lg px-3 py-1.5 text-xs text-foreground focus:outline-none focus:border-primary"
                        />
                      </div>
                      <div className="flex-1">
                        <label className="block text-[10px] text-foreground-muted mb-1">Max Replicas</label>
                        <input
                          type="number"
                          value={maxReplicas}
                          onChange={(e) => setMaxReplicas(parseInt(e.target.value))}
                          className="w-full bg-card border border-border rounded-lg px-3 py-1.5 text-xs text-foreground focus:outline-none focus:border-primary"
                        />
                      </div>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-foreground-muted uppercase tracking-wider mb-1.5">Deployment Mode</label>
                    <div className="flex gap-4">
                      {["standard", "canary"].map((mode) => (
                        <label key={mode} className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
                          <input
                            type="radio"
                            name="deploy_mode"
                            value={mode}
                            checked={deployMode === mode}
                            onChange={() => setDeployMode(mode)}
                            className="accent-primary"
                          />
                          <span className="capitalize">{mode}</span>
                        </label>
                      ))}
                    </div>
                  </div>
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
                  onClick={() => {
                    addToast(`Launching deployment for ${selectedRepo}...`, "info");
                    addRepository({
                      name: selectedRepo.split("/").pop() || selectedRepo,
                      fullName: selectedRepo,
                      framework: detectedFramework,
                      language: detectedFramework === "FastAPI" ? "Python" : "TypeScript",
                    });
                    
                    // Route to deployments simulation page with details
                    router.push(`/dashboard/deployments?id=onboard-run&repo=${encodeURIComponent(selectedRepo)}&mode=fallback`);
                  }}
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

  const handleConnect = (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoName.trim()) return;

    setIsSubmitting(true);
    const fullName = repoName.includes("/") ? repoName.trim() : `acme/${repoName.trim()}`;
    const name = fullName.split("/")[1] || fullName;
    const language = frameworkToLanguage[framework] || "TypeScript";

    setTimeout(() => {
      addRepository({
        name,
        fullName,
        framework,
        language
      });
      setIsSubmitting(false);
      setIsModalOpen(false);
      setRepoName("");
      
      addToast(`Connected repository ${fullName} successfully!`, "success");
      addNotification({
        title: "Repository Connected",
        message: `Successfully connected ${fullName} framework: ${framework}. Initializing automated code review...`,
        type: "success"
      });
    }, 1200);
  };

  const handleCardAction = async (action: string, repo: string) => {
    if (action === "Analyze") {
      addToast(`Initiating AI security and performance review for ${repo}...`, "info");
      try {
        const metadataRes = await fetch(`/api/github/repo-metadata?repo=${encodeURIComponent(repo)}`);
        if (metadataRes.ok) {
          const metadata = await metadataRes.json();
          setBranchesByRepo((prev) => ({ ...prev, [repo]: metadata.branches || ["main"] }));
        } else {
          setBranchesByRepo((prev) => ({ ...prev, [repo]: ["main", "develop", "feature/auth"] }));
        }

        const res = await fetch("/api/ai/analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ repo, branch: "main" }),
        });
        if (!res.ok) throw new Error("Failed analysis");
        const data = await res.json();
        
        addToast(`AI scan complete. Framework: ${data.framework} (${data.version}), Risk Score: ${data.risk_score}`, "success");
        addNotification({
          title: "AI Analysis Complete",
          message: `Scan finished on ${repo}. Framework: ${data.framework}. Recommended resources: CPU: ${data.resources.cpu}, RAM: ${data.resources.memory}.`,
          type: "success"
        });
      } catch (err) {
        console.error("AI Analysis failed:", err);
        const fallback = createFallbackAnalysis(repo);
        setBranchesByRepo((prev) => ({ ...prev, [repo]: ["main", "develop", "feature/auth"] }));
        addToast(`Local fallback analysis complete. Framework: ${fallback.framework}, Risk Score: ${fallback.risk_score}`, "warning");
        addNotification({
          title: "Fallback Analysis Complete",
          message: `Generated deployment recommendations for ${repo} using the local ZeroOps analyzer.`,
          type: "info",
        });
      }
    } else if (action === "Deploy") {
      addToast(`Triggering deployment pipeline for ${repo}...`, "info");
      try {
        const res = await fetch("/api/deployments/deploy", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ repo, branch: "main" }),
        });
        if (!res.ok) throw new Error("Deploy trigger failed");
        const data = await res.json();
        if (data.status === "success") {
          addToast("Pipeline successfully initialized.", "success");
          router.push(`/dashboard/deployments?id=${data.deployment_id}&repo=${encodeURIComponent(repo)}`);
        }
      } catch (err) {
        console.error("Deployment trigger failed:", err);
        addToast("Deployment backend unavailable. Starting guided pipeline simulation.", "warning");
        router.push(`/dashboard/deployments?id=demo-${repo.split("/").pop()}&repo=${encodeURIComponent(repo)}&mode=fallback`);
      }
    } else if (action === "Logs") {
      router.push("/dashboard/logs");
    }
  };

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
          { label: "Connected", value: repositories.length.toString(), icon: GitBranch }, 
          { label: "Production", value: repositories.filter(r => r.deploymentStatus === "running").length.toString(), icon: Play }, 
          { label: "Total Deployments", value: repositories.reduce((sum, r) => sum + r.totalDeployments, 0).toString(), icon: Terminal }
        ].map((s, i) => (
          <motion.div key={s.label} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }} className="glass rounded-xl p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center"><s.icon size={18} className="text-primary" /></div>
            <div><p className="text-2xl font-bold text-foreground">{s.value}</p><p className="text-xs text-foreground-muted">{s.label}</p></div>
          </motion.div>
        ))}
      </div>

      {/* Search */}
      <div className="flex gap-3">
        <div className="flex-1 glass-subtle rounded-xl px-4 py-2.5 flex items-center gap-2">
          <Search size={16} className="text-foreground-muted" />
          <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search repositories..." className="bg-transparent border-none outline-none text-sm text-foreground placeholder:text-foreground-muted w-full" />
        </div>
      </div>

      {/* Repo cards */}
      <div className="grid lg:grid-cols-2 gap-4">
        {filtered.map((repo, i) => (
          <motion.div key={repo.id} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }}
            className="glass rounded-xl p-5 hover:bg-card-hover/50 transition-all group">
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <GitBranch size={20} className="text-foreground-muted" />
                <div>
                  <h3 className="font-semibold text-foreground group-hover:text-primary transition-colors">{repo.fullName}</h3>
                  <p className="text-xs text-foreground-muted">{repo.lastCommitMessage}</p>
                  <p className="text-[10px] text-foreground-muted mt-0.5">
                    Branches: {(branchesByRepo[repo.fullName] || ["main"]).join(", ")}
                  </p>
                </div>
              </div>
              <StatusBadge status={repo.deploymentStatus} />
            </div>
            <div className="flex items-center gap-3 mb-4">
              <span className={`text-xs px-2 py-1 rounded-full ${frameworkColors[repo.framework] || "bg-card text-foreground-muted"}`}>{repo.framework}</span>
              <span className="flex items-center gap-1 text-xs text-foreground-muted">
                <span className={`w-2.5 h-2.5 rounded-full ${langColors[repo.language] || "bg-gray-500"}`} />{repo.language}
              </span>
              <span className="text-xs text-foreground-muted font-semibold">⭐ {repo.stars}</span>
              <span className="text-xs text-foreground-muted">{repo.totalDeployments} deploys</span>
            </div>
            <div className="flex items-center gap-2">
              {[
                { icon: Brain, label: "Analyze" }, 
                { icon: Play, label: "Deploy" }, 
                { icon: Terminal, label: "Logs" }
              ].map(action => (
                <button 
                  key={action.label} 
                  onClick={() => handleCardAction(action.label, repo.fullName)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium glass-subtle hover:bg-card-hover/80 text-foreground-muted hover:text-foreground transition-colors cursor-pointer"
                >
                  <action.icon size={14} />{action.label}
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
              Connect a GitHub repository or PAT-backed repo path to let ZeroOps configure and deploy it.
            </p>

            <form onSubmit={handleConnect} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-foreground-muted mb-1.5">Repository Path</label>
                <input 
                  type="text" 
                  value={repoName}
                  onChange={e => setRepoName(e.target.value)}
                  placeholder="e.g. acme/billing-service" 
                  className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none placeholder:text-foreground-muted"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-foreground-muted mb-1.5">Framework / Runtime</label>
                <select 
                  value={framework}
                  onChange={e => setFramework(e.target.value)}
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
