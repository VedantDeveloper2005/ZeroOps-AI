"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ArrowLeft, ArrowRight, CheckCircle2, ChevronDown, FileArchive, FolderGit2, GitBranch, Loader2, Search, ShieldCheck, Sparkles, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { useNotifications } from "@/lib/NotificationContext";
import { api, getErrorMessage, type GitHubRepoItem } from "@/lib/api";

type AppReview = {
  framework: string | null;
  applicationType: string | null;
  explanation: string | null;
  environmentVariables: string[];
  estimatedBuildTime: string | null;
};

const asString = (value: unknown) => typeof value === "string" && value.trim() ? value : null;
const asStrings = (value: unknown) => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : [];

const toReview = (data: Record<string, unknown>): AppReview => ({
  framework: asString(data.framework),
  applicationType: asString(data.application_type),
  explanation: asString(data.explanation),
  environmentVariables: asStrings(data.environment_variables),
  estimatedBuildTime: asString(data.estimated_build_time),
});

const sourceDate = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Recently updated" : `Updated ${date.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
};

export default function RepositoriesPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const { user, loginWithGitHub } = useAuth();
  const { addToast, refreshProjects, refreshStats } = useNotifications();
  const [repos, setRepos] = useState<GitHubRepoItem[]>([]);
  const [repoSearch, setRepoSearch] = useState("");
  const [selectedRepo, setSelectedRepo] = useState<GitHubRepoItem | null>(null);
  const [branch, setBranch] = useState("main");
  const [branches, setBranches] = useState<string[]>(["main"]);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [loadingBranches, setLoadingBranches] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadedProjectId, setUploadedProjectId] = useState<string | null>(null);
  const [sourceName, setSourceName] = useState<string | null>(null);
  const [review, setReview] = useState<AppReview | null>(null);
  const [isReviewing, setIsReviewing] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const githubConnected = user?.github_connected === true;

  const loadRepos = useCallback(async (query = "") => {
    if (!githubConnected) return;
    setLoadingRepos(true);
    try {
      const result = await api.getGitHubRepos({ page: 1, per_page: 50, sort: "updated", q: query || undefined });
      setRepos(result.repos);
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't load your repositories. Please try again."));
    } finally {
      setLoadingRepos(false);
    }
  }, [githubConnected]);

  useEffect(() => {
    if (!githubConnected) return;
    const timer = window.setTimeout(() => loadRepos(repoSearch), 250);
    return () => window.clearTimeout(timer);
  }, [githubConnected, loadRepos, repoSearch]);

  useEffect(() => {
    if (!selectedRepo) return;
    setLoadingBranches(true);
    api.getRepoBranches(selectedRepo.full_name)
      .then((result) => {
        const available = result.branches.length ? result.branches : [selectedRepo.default_branch || "main"];
        setBranches(available);
        setBranch(available.includes(selectedRepo.default_branch) ? selectedRepo.default_branch : available[0]);
      })
      .catch(() => {
        const fallback = selectedRepo.default_branch || "main";
        setBranches([fallback]);
        setBranch(fallback);
      })
      .finally(() => setLoadingBranches(false));
  }, [selectedRepo]);

  const resetReview = () => {
    setReview(null);
    setError(null);
  };

  const chooseRepository = (repo: GitHubRepoItem) => {
    setSelectedRepo(repo);
    setUploadedProjectId(null);
    setUploadFile(null);
    setSourceName(repo.full_name);
    resetReview();
  };

  const inspectRepository = async () => {
    if (!selectedRepo) return;
    setIsReviewing(true);
    setError(null);
    try {
      const result = await api.analyzeRepo(selectedRepo.full_name, branch);
      setReview(toReview(result));
      addToast("Your application is ready to review.", "success");
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't review this repository. Please try again."));
    } finally {
      setIsReviewing(false);
    }
  };

  const uploadCode = async () => {
    if (!uploadFile) return;
    setIsUploading(true);
    setError(null);
    try {
      const result = await api.uploadCode(uploadFile);
      setUploadedProjectId(result.project.id);
      setSourceName(uploadFile.name);
      setSelectedRepo(null);
      setBranch(result.project.branch || "uploaded");
      setReview(toReview(result.analysis));
      await Promise.all([refreshProjects(), refreshStats()]);
      addToast("Your application is ready to review.", "success");
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't process that ZIP file. Check it and try again."));
    } finally {
      setIsUploading(false);
    }
  };

  const launch = async () => {
    if (!review || !sourceName) return;
    setIsLaunching(true);
    setError(null);
    try {
      const targets = await api.getDeploymentTargets();
      if (!targets.any_ready) {
        setError("Connect a hosting account before you launch. The advanced setup keeps these details out of your day-to-day workspace.");
        return;
      }
      const project = uploadedProjectId
        ? await api.getProject(uploadedProjectId)
        : await api.createProject({
          name: selectedRepo?.name || sourceName.replace(/\.zip$/i, ""),
          full_name: selectedRepo?.full_name || sourceName,
          repo_url: selectedRepo?.html_url,
          framework: review.framework || "Unknown",
          language: selectedRepo?.language || "Unknown",
          branch,
          region: "eastus",
        });
      const result = await api.startDeployment({ project_id: project.id, branch, environment: "production" });
      await Promise.all([refreshProjects(), refreshStats()]);
      addToast("Launch started.", "success");
      router.push(`/dashboard/deployments?id=${result.deployment_id}&repo=${encodeURIComponent(sourceName)}`);
    } catch (err) {
      setError(getErrorMessage(err, "We couldn't start the launch. Please try again."));
    } finally {
      setIsLaunching(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-7 pb-10">
      <section className="text-center"><span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 text-[10px] font-bold tracking-wide text-primary"><Sparkles size={12} /> NEW APPLICATION</span><h1 className="mt-4 text-3xl font-bold tracking-tight text-foreground">Start with your code.</h1><p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-foreground-muted">Choose a source. We&apos;ll prepare the application in the background and only bring you the choices that need your attention.</p></section>

      {error && <div className="flex flex-col gap-3 rounded-2xl border border-warning/25 bg-warning/10 p-4 text-sm text-foreground sm:flex-row sm:items-center sm:justify-between"><span>{error}</span>{error.startsWith("Connect a hosting") && <button onClick={() => router.push("/dashboard/settings")} className="shrink-0 rounded-lg bg-card px-3 py-2 text-xs font-bold text-foreground transition hover:bg-card-hover">Open advanced setup</button>}</div>}

      {!review && <>
        <section className="grid gap-4 md:grid-cols-2">
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="rounded-2xl border border-border bg-card p-6 shadow-sm"><div className="grid h-11 w-11 place-items-center rounded-xl bg-foreground text-background"><GitBranch size={21} /></div><h2 className="mt-5 text-lg font-bold text-foreground">Connect GitHub</h2><p className="mt-1.5 text-sm leading-6 text-foreground-muted">Pick a repository and branch without leaving your workspace.</p>{githubConnected ? <div className="mt-5 flex items-center gap-2 text-xs font-semibold text-success"><CheckCircle2 size={15} /> Connected as @{user?.github_username || "GitHub"}</div> : <button onClick={loginWithGitHub} className="mt-5 inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-xs font-bold text-white transition hover:bg-primary-hover"><GitBranch size={15} /> Connect GitHub</button>}</motion.div>
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }} className="rounded-2xl border border-border bg-card p-6 shadow-sm"><div className="grid h-11 w-11 place-items-center rounded-xl bg-primary/10 text-primary"><FileArchive size={21} /></div><h2 className="mt-5 text-lg font-bold text-foreground">Upload a ZIP</h2><p className="mt-1.5 text-sm leading-6 text-foreground-muted">Use a ZIP file when the code isn&apos;t in GitHub yet.</p><input ref={inputRef} type="file" accept=".zip,application/zip,application/x-zip-compressed" className="hidden" onChange={(event) => { setUploadFile(event.target.files?.[0] || null); resetReview(); }} /><div className="mt-5 flex flex-wrap items-center gap-2"><button onClick={() => inputRef.current?.click()} className="inline-flex items-center gap-2 rounded-xl border border-border bg-background-secondary px-4 py-2.5 text-xs font-bold text-foreground transition hover:bg-card-hover"><Upload size={15} /> Choose ZIP</button>{uploadFile && <button onClick={uploadCode} disabled={isUploading} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-xs font-bold text-white transition hover:bg-primary-hover disabled:opacity-60">{isUploading ? <Loader2 size={15} className="animate-spin" /> : <ArrowRight size={15} />} Review {uploadFile.name}</button>}</div></motion.div>
        </section>

        {githubConnected && <section className="rounded-2xl border border-border bg-card p-5 shadow-sm"><div className="flex flex-col gap-3 border-b border-border/60 pb-4 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="text-base font-bold text-foreground">Choose a repository</h2><p className="mt-0.5 text-xs text-foreground-muted">Only the repository you select is used for this application.</p></div><label className="flex w-full items-center gap-2 rounded-lg border border-border bg-background-secondary px-3 py-2 sm:w-64"><Search size={14} className="text-foreground-muted" /><input value={repoSearch} onChange={(event) => setRepoSearch(event.target.value)} placeholder="Find a repository" className="w-full bg-transparent text-xs text-foreground outline-none placeholder:text-foreground-muted" /></label></div>
          {loadingRepos ? <div className="flex h-40 items-center justify-center"><Loader2 size={20} className="animate-spin text-primary" /></div> : repos.length === 0 ? <div className="py-10 text-center"><FolderGit2 size={28} className="mx-auto text-foreground-muted/40" /><p className="mt-3 text-sm text-foreground-muted">No repositories found.</p></div> : <div className="mt-4 grid gap-2 sm:grid-cols-2">{repos.map((repo) => <button key={repo.id} onClick={() => chooseRepository(repo)} className={`rounded-xl border p-4 text-left transition ${selectedRepo?.id === repo.id ? "border-primary bg-primary/5" : "border-border hover:border-border-hover hover:bg-card-hover/40"}`}><div className="flex items-center justify-between gap-3"><span className="truncate text-sm font-bold text-foreground">{repo.name}</span>{selectedRepo?.id === repo.id && <CheckCircle2 size={16} className="shrink-0 text-primary" />}</div><p className="mt-1 truncate text-xs text-foreground-muted">{repo.full_name}</p><div className="mt-3 flex items-center justify-between text-[10px] font-medium text-foreground-muted"><span>{repo.language || "Code repository"}</span><span>{sourceDate(repo.updated_at)}</span></div></button>)}</div>}
          {selectedRepo && <div className="mt-5 flex flex-col gap-3 rounded-xl bg-background-secondary p-4 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-xs font-bold text-foreground">{selectedRepo.full_name}</p><p className="mt-0.5 text-[11px] text-foreground-muted">You can change this before review.</p></div><div className="flex items-center gap-2">{loadingBranches ? <Loader2 size={15} className="animate-spin text-primary" /> : <div className="relative"><select value={branch} onChange={(event) => setBranch(event.target.value)} className="appearance-none rounded-lg border border-border bg-card py-2 pl-3 pr-8 text-xs font-semibold text-foreground outline-none">{branches.map((option) => <option key={option}>{option}</option>)}</select><ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-2.5 text-foreground-muted" /></div>}<button onClick={inspectRepository} disabled={isReviewing || loadingBranches} className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-xs font-bold text-white transition hover:bg-primary-hover disabled:opacity-60">{isReviewing ? <Loader2 size={14} className="animate-spin" /> : <ArrowRight size={14} />} Review app</button></div></div>}
        </section>}
      </>}

      {review && <motion.section initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} className="rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-7"><div className="flex flex-col gap-4 border-b border-border/60 pb-5 sm:flex-row sm:items-start sm:justify-between"><div><span className="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-2.5 py-1 text-[10px] font-bold text-success"><CheckCircle2 size={12} /> READY TO REVIEW</span><h2 className="mt-3 text-xl font-bold text-foreground">{sourceName}</h2><p className="mt-1 text-sm text-foreground-muted">Here&apos;s what we found. The technical setup stays in the background.</p></div><button onClick={() => { setReview(null); setError(null); }} className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs font-bold text-foreground-muted transition hover:bg-card-hover"><ArrowLeft size={14} /> Change source</button></div>
        <div className="mt-6 grid gap-4 md:grid-cols-3"><div className="rounded-xl bg-background-secondary p-4"><p className="text-[10px] font-bold uppercase tracking-wide text-foreground-muted">Application</p><p className="mt-2 text-sm font-bold text-foreground">{review.applicationType || "Application detected"}</p></div><div className="rounded-xl bg-background-secondary p-4"><p className="text-[10px] font-bold uppercase tracking-wide text-foreground-muted">Framework</p><p className="mt-2 text-sm font-bold text-foreground">{review.framework || "Detected during setup"}</p></div><div className="rounded-xl bg-background-secondary p-4"><p className="text-[10px] font-bold uppercase tracking-wide text-foreground-muted">Preparation</p><p className="mt-2 text-sm font-bold text-foreground">{review.estimatedBuildTime || "Ready to launch"}</p></div></div>
        {review.explanation && <div className="mt-4 rounded-xl border border-primary/15 bg-primary/[0.04] p-4"><p className="text-xs font-bold text-primary">What we&apos;ll handle</p><p className="mt-1.5 text-sm leading-6 text-foreground-muted">{review.explanation}</p></div>}
        <div className="mt-4 rounded-xl border border-border bg-background-secondary/60 p-4"><p className="text-xs font-bold text-foreground">Configuration</p>{review.environmentVariables.length > 0 ? <><p className="mt-1 text-xs text-foreground-muted">Add these values after launch if your application requires them.</p><div className="mt-3 flex flex-wrap gap-2">{review.environmentVariables.map((variable) => <span key={variable} className="rounded-md border border-border bg-card px-2 py-1 font-mono text-[11px] text-foreground-muted">{variable}</span>)}</div></> : <p className="mt-1 text-xs text-foreground-muted">No configuration values were detected.</p>}</div>
        <div className="mt-6 flex flex-col gap-4 rounded-xl border border-success/20 bg-success/[0.04] p-5 sm:flex-row sm:items-center sm:justify-between"><div className="flex gap-3"><ShieldCheck size={20} className="mt-0.5 shrink-0 text-success" /><div><p className="text-sm font-bold text-foreground">You approve the launch.</p><p className="mt-1 text-xs leading-5 text-foreground-muted">We&apos;ll only show you progress and decisions that need your input. You can review activity at any time.</p></div></div><button onClick={launch} disabled={isLaunching} className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-bold text-white transition hover:bg-primary-hover disabled:opacity-60">{isLaunching ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />} Launch application</button></div>
      </motion.section>}
    </div>
  );
}
