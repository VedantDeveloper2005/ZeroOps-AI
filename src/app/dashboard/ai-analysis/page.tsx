"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Box,
  Braces,
  Clock3,
  Code2,
  FileSearch,
  History,
  Loader2,
  PackageSearch,
  Play,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { ProjectSelector } from "@/components/dashboard/ProjectSelector";
import { ProjectTabs } from "@/components/dashboard/ProjectTabs";
import { useNotifications } from "@/lib/NotificationContext";
import { api, getErrorMessage, type AIAnalysis } from "@/lib/api";

function formatTimestamp(value: string | null) {
  if (!value) return "Time not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Time not recorded";
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Fact({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string | null | undefined;
  icon: typeof Code2;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface-subtle p-4">
      <div className="flex items-center gap-2 text-xs font-medium text-foreground-muted">
        <Icon size={15} />
        {label}
      </div>
      <p className="mt-2 break-words text-sm font-semibold text-foreground">
        {value?.trim() || "Not detected"}
      </p>
    </div>
  );
}

export default function AIAnalysisPage() {
  return (
    <Suspense fallback={<AnalysisLoading />}>
      <AnalysisWorkspace />
    </Suspense>
  );
}

function AnalysisWorkspace() {
  const searchParams = useSearchParams();
  const { projects, isLoading: projectsLoading, addToast } = useNotifications();
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [analyses, setAnalyses] = useState<AIAnalysis[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const requestedProject = searchParams.get("project");
    if (requestedProject && projects.some((project) => project.id === requestedProject)) {
      setSelectedProjectId(requestedProject);
      return;
    }
    if (!selectedProjectId && projects.length > 0) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, searchParams, selectedProjectId]);

  const loadAnalyses = useCallback(async (projectId: string) => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      setAnalyses(await api.getAIAnalysisHistory(projectId));
    } catch (requestError) {
      setAnalyses([]);
      setError(getErrorMessage(requestError, "Repository analysis could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAnalyses(selectedProjectId);
  }, [loadAnalyses, selectedProjectId]);

  const runAnalysis = async () => {
    if (!selectedProjectId || running) return;
    setRunning(true);
    setError(null);
    try {
      await api.analyzeRepository(selectedProjectId);
      await loadAnalyses(selectedProjectId);
      addToast("Repository analysis completed and was saved.", "success");
    } catch (requestError) {
      const message = getErrorMessage(requestError, "Repository analysis could not be completed.");
      setError(message);
      addToast(message, "error");
    } finally {
      setRunning(false);
    }
  };

  if (projectsLoading) return <AnalysisLoading />;

  if (projects.length === 0) {
    return (
      <StatePanel
        title="No repository to analyze"
        description="Connect GitHub or upload a ZIP so ZeroOps can inspect real source files."
        action={{ label: "Connect a project", href: "/dashboard/repositories" }}
      />
    );
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const latest = analyses[0] ?? null;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Project intelligence"
        title="Repository analysis"
        description="Recorded source-analysis output for framework, runtime, build, and deployment requirements. This is not a live runtime audit or a complete CVE scan."
        actions={
          <>
            <Link
              href={`/dashboard/ai-analysis/history?project=${selectedProjectId}`}
              className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground shadow-sm transition-colors hover:bg-surface-raised"
            >
              <History size={15} />
              History
            </Link>
            <button
              type="button"
              onClick={() => void runAnalysis()}
              disabled={running || !selectedProjectId}
              className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-primary px-4 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-primary-hover disabled:opacity-50"
            >
              <RefreshCw size={15} className={running ? "animate-spin" : ""} />
              {running ? "Analyzing…" : latest ? "Run again" : "Run analysis"}
            </button>
          </>
        }
      />

      <ProjectSelector
        projects={projects}
        value={selectedProjectId}
        onChange={setSelectedProjectId}
        className="block max-w-sm"
      />

      {selectedProject && <ProjectTabs projectId={selectedProject.id} />}

      {error && (
        <StatePanel
          variant="error"
          compact
          title="Analysis is unavailable"
          description={error}
          action={{ label: "Try again", onClick: () => void loadAnalyses(selectedProjectId) }}
        />
      )}

      {loading ? (
        <AnalysisLoading compact />
      ) : !latest ? (
        <StatePanel
          variant="info"
          title="No saved analysis for this project"
          description="Run analysis to inspect the connected source snapshot. Results are recommendations and must be reviewed before deployment."
          action={{ label: "Run analysis", onClick: () => void runAnalysis() }}
        />
      ) : (
        <>
          <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
            <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h2 className="text-base font-semibold text-foreground">Latest recorded result</h2>
                <p className="mt-1 flex items-center gap-1.5 text-xs text-foreground-muted">
                  <Clock3 size={13} />
                  {formatTimestamp(latest.created_at)}
                </p>
              </div>
              <span className="w-fit rounded-full border border-border bg-surface-subtle px-2.5 py-1 text-[11px] font-medium text-foreground-muted">
                {analyses.length} saved {analyses.length === 1 ? "run" : "runs"}
              </span>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Fact
                label="Framework"
                value={[latest.framework, latest.framework_version].filter(Boolean).join(" ")}
                icon={Braces}
              />
              <Fact label="Language / runtime" value={latest.runtime || latest.language} icon={Code2} />
              <Fact label="Package manager" value={latest.package_manager} icon={PackageSearch} />
              <Fact
                label="Container support"
                value={latest.docker_support ? "Docker configuration detected" : "Not detected"}
                icon={Box}
              />
            </div>
          </section>

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(300px,0.7fr)]">
            <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
              <div className="flex items-center gap-2">
                <FileSearch size={17} className="text-primary" />
                <h2 className="text-sm font-semibold text-foreground">Build and runtime findings</h2>
              </div>
              <dl className="mt-4 divide-y divide-border rounded-lg border border-border">
                {[
                  ["Application type", latest.application_type],
                  ["Build command", latest.build_commands],
                  ["Start command", latest.start_commands],
                  ["Detected port", latest.port],
                  ["Deployment strategy", latest.deployment_strategy],
                  ["Monorepo structure", latest.monorepo_structure],
                ].map(([label, value]) => (
                  <div key={label} className="grid gap-1 px-4 py-3 sm:grid-cols-[160px_1fr] sm:gap-4">
                    <dt className="text-xs font-medium text-foreground-muted">{label}</dt>
                    <dd className="break-words font-mono text-xs text-foreground">
                      {value?.trim() || "Not detected"}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>

            <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
              <div className="flex items-center gap-2">
                <ShieldAlert size={17} className="text-warning" />
                <h2 className="text-sm font-semibold text-foreground">Analysis warnings</h2>
              </div>
              <p className="mt-2 text-xs leading-5 text-foreground-muted">
                These are analyzer findings, not independently verified vulnerabilities.
              </p>
              {latest.vulnerabilities.length > 0 ? (
                <ul className="mt-4 space-y-2">
                  {latest.vulnerabilities.map((warning, index) => (
                    <li
                      key={`${warning}-${index}`}
                      className="rounded-lg border border-warning/25 bg-warning-subtle px-3 py-2.5 text-xs leading-5 text-foreground"
                    >
                      {warning}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-4 rounded-lg border border-border bg-surface-subtle px-3 py-4 text-xs text-foreground-muted">
                  No warnings were saved with this analysis. This does not replace dependency or container scanning.
                </p>
              )}
            </section>
          </div>

          <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
            <div className="flex items-center gap-2">
              <Play size={17} className="text-primary" />
              <h2 className="text-sm font-semibold text-foreground">Detected dependencies</h2>
            </div>
            {latest.dependencies.length > 0 ? (
              <ul className="mt-4 flex flex-wrap gap-2">
                {latest.dependencies.map((dependency) => (
                  <li
                    key={dependency}
                    className="rounded-md border border-border bg-surface-subtle px-2.5 py-1.5 font-mono text-[11px] text-foreground"
                  >
                    {dependency}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-xs text-foreground-muted">No dependency names were saved.</p>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function AnalysisLoading({ compact = false }: { compact?: boolean }) {
  return (
    <div
      role="status"
      className={`flex items-center justify-center gap-3 rounded-xl border border-border bg-card text-sm font-medium text-foreground-muted ${
        compact ? "min-h-52" : "min-h-[55vh]"
      }`}
    >
      <Loader2 size={18} className="animate-spin text-primary" />
      Loading saved analysis…
    </div>
  );
}
