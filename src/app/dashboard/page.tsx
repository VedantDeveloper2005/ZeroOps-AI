"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, CheckCircle2, Clock3, ExternalLink, FolderPlus, Rocket, Sparkles } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { useNotifications } from "@/lib/NotificationContext";
import { api, type Deployment } from "@/lib/api";

const formatDate = (value?: string | null) => {
  if (!value) return "Not launched yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not launched yet";
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

const statusLabel = (status?: string | null) => {
  if (["running", "success", "completed", "active"].includes(status || "")) return { label: "Live", className: "bg-success/10 text-success border-success/20" };
  if (["building", "deploying", "pending", "queued"].includes(status || "")) return { label: "In progress", className: "bg-primary/10 text-primary border-primary/20" };
  if (["failed", "error"].includes(status || "")) return { label: "Needs attention", className: "bg-danger/10 text-danger border-danger/20" };
  return { label: "Ready to launch", className: "bg-background-secondary text-foreground-muted border-border" };
};

export default function DashboardHome() {
  const { user } = useAuth();
  const { projects, isLoading: projectsLoading } = useNotifications();
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [loadingDeployments, setLoadingDeployments] = useState(true);

  useEffect(() => {
    let active = true;
    api.getDeployments(50)
      .then((data) => { if (active) setDeployments(data); })
      .catch(() => { if (active) setDeployments([]); })
      .finally(() => { if (active) setLoadingDeployments(false); });
    return () => { active = false; };
  }, []);

  const latestByProject = useMemo(() => {
    const records = new Map<string, Deployment>();
    for (const deployment of deployments) {
      const previous = records.get(deployment.project_id);
      const currentTime = new Date(deployment.completed_at || deployment.started_at || 0).getTime();
      const previousTime = new Date(previous?.completed_at || previous?.started_at || 0).getTime();
      if (!previous || currentTime > previousTime) records.set(deployment.project_id, deployment);
    }
    return records;
  }, [deployments]);

  const firstName = user?.first_name || user?.firstName || "there";
  const isLoading = projectsLoading || loadingDeployments;

  if (isLoading) {
    return <div className="flex min-h-[55vh] items-center justify-center"><span className="h-7 w-7 animate-spin rounded-full border-2 border-primary border-t-transparent" /></div>;
  }

  return (
    <div className="mx-auto max-w-5xl space-y-9 pb-10">
      <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }} className="relative overflow-hidden rounded-3xl border border-border bg-card px-6 py-8 shadow-sm sm:px-8">
        <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <div className="max-w-xl">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-bold text-primary"><Sparkles size={12} /> YOUR WORKSPACE</span>
            <h1 className="mt-4 text-3xl font-bold tracking-tight text-foreground">Good to see you, {firstName}.</h1>
            <p className="mt-2 text-sm leading-6 text-foreground-muted">Everything important about your applications is here. The platform details stay out of your way.</p>
          </div>
          <Link href="/dashboard/repositories" className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-bold text-white shadow-md shadow-primary/15 transition hover:bg-primary-hover"><FolderPlus size={16} /> Add application</Link>
        </div>
      </motion.section>

      {projects.length === 0 ? (
        <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08, duration: 0.35 }} className="rounded-3xl border border-border bg-card p-8 text-center shadow-sm sm:p-12">
          <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-primary/10 text-primary"><Rocket size={25} /></div>
          <h2 className="mt-5 text-xl font-bold text-foreground">Bring your first application</h2>
          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-foreground-muted">Connect a repository or upload a ZIP. You&apos;ll review the essentials before anything goes live.</p>
          <Link href="/dashboard/repositories" className="mt-6 inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-bold text-white transition hover:bg-primary-hover">Choose your code <ArrowRight size={16} /></Link>
        </motion.section>
      ) : (
        <section>
          <div className="mb-4 flex items-center justify-between"><div><h2 className="text-lg font-bold text-foreground">Your applications</h2><p className="mt-0.5 text-xs text-foreground-muted">Current status from your workspace.</p></div><span className="text-xs font-semibold text-foreground-muted">{projects.length} total</span></div>
          <div className="grid gap-3">
            {projects.map((project, index) => {
              const deployment = latestByProject.get(project.id);
              const status = statusLabel(deployment?.status || project.latest_deployment_status || project.status);
              const source = project.full_name.startsWith("upload/") ? "Uploaded code" : project.full_name;
              return (
                <motion.article key={project.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.05 }} className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-5 shadow-sm transition hover:border-border-hover sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="truncate font-bold text-foreground">{project.name}</h3><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${status.className}`}>{status.label}</span></div><p className="mt-1 truncate text-xs text-foreground-muted">{source}</p><p className="mt-3 flex items-center gap-1.5 text-[11px] font-medium text-foreground-muted"><Clock3 size={12} /> {formatDate(deployment?.completed_at || deployment?.started_at || project.last_deployed_at)}</p></div>
                  <div className="flex shrink-0 items-center gap-2">
                    {deployment?.live_url && <a href={deployment.live_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs font-semibold text-foreground-muted transition hover:bg-card-hover hover:text-foreground">Visit <ExternalLink size={13} /></a>}
                    <Link href={`/dashboard/apps/${project.id}`} className="inline-flex items-center gap-1.5 rounded-lg bg-background-secondary px-3 py-2 text-xs font-bold text-foreground transition hover:bg-card-hover">Open <ArrowRight size={13} /></Link>
                  </div>
                </motion.article>
              );
            })}
          </div>
        </section>
      )}

      {deployments.length > 0 && <section className="rounded-2xl border border-border bg-card p-5 shadow-sm"><div className="mb-4 flex items-center justify-between"><div><h2 className="text-base font-bold text-foreground">Recent activity</h2><p className="mt-0.5 text-xs text-foreground-muted">A clear record of what has happened.</p></div><CheckCircle2 size={18} className="text-success" /></div><div className="divide-y divide-border/60">{deployments.slice(0, 4).map((deployment) => { const status = statusLabel(deployment.status); return <Link key={deployment.id} href={`/dashboard/deployments?id=${deployment.id}`} className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0 transition hover:opacity-70"><div className="min-w-0"><p className="truncate text-sm font-semibold text-foreground">{deployment.project_name || "Application update"}</p><p className="mt-0.5 text-xs text-foreground-muted">{formatDate(deployment.completed_at || deployment.started_at)}</p></div><span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-bold ${status.className}`}>{status.label}</span></Link>; })}</div></section>}
    </div>
  );
}
