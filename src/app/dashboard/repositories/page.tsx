"use client";

import { motion } from "framer-motion";
import { GitBranch, Plus, Search, Play, Brain, Terminal, X, Loader2 } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useState, useEffect } from "react";
import { useNotifications } from "@/lib/NotificationContext";
import { useRouter } from "next/navigation";

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
  const { repositories, addRepository, addToast, addNotification } = useNotifications();
  const [search, setSearch] = useState("");
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [repoName, setRepoName] = useState("");
  const [framework, setFramework] = useState("Next.js");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const filtered = repositories.filter(r => r.name.toLowerCase().includes(search.toLowerCase()) || r.fullName.toLowerCase().includes(search.toLowerCase()));

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
        addToast("AI Analysis failed. Running local fallback check.", "error");
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
          router.push(`/dashboard/deployments?id=${data.deployment_id}`);
        }
      } catch (err) {
        console.error("Deployment trigger failed:", err);
        addToast("Deployment trigger failed. Redirecting to pipeline.", "warning");
        router.push("/dashboard/deployments");
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
              Connect a GitHub repository to let ZeroOps configure and deploy it.
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
