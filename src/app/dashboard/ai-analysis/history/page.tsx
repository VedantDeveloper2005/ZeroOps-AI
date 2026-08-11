"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ChevronDown, ChevronUp, Clock3, Loader2 } from "lucide-react";
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
  return date.toLocaleString();
}

export default function AIAnalysisHistoryPage() {
  return (
    <Suspense fallback={<HistoryLoading />}>
      <AnalysisHistory />
    </Suspense>
  );
}

function AnalysisHistory() {
  const searchParams = useSearchParams();
  const { projects, isLoading: projectsLoading } = useNotifications();
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [analyses, setAnalyses] = useState<AIAnalysis[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const requestedProject = searchParams.get("project");
    if (requestedProject && projects.some((project) => project.id === requestedProject)) {
      setSelectedProjectId(requestedProject);
      return;
    }
    if (!selectedProjectId && projects.length > 0) setSelectedProjectId(projects[0].id);
  }, [projects, searchParams, selectedProjectId]);

  const loadHistory = useCallback(async (projectId: string) => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      setAnalyses(await api.getAIAnalysisHistory(projectId));
    } catch (requestError) {
      setAnalyses([]);
      setError(getErrorMessage(requestError, "Saved analysis history could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHistory(selectedProjectId);
  }, [loadHistory, selectedProjectId]);

  const selectProject = (projectId: string) => {
    setAnalyses([]);
    setExpandedId(null);
    setError(null);
    setLoading(true);
    setSelectedProjectId(projectId);
  };

  if (projectsLoading) return <HistoryLoading />;

  if (projects.length === 0) {
    return (
      <div>
        <PageHeader
          eyebrow="Repository analysis"
          title="Saved analysis history"
          description="Review durable source-analysis records without inferring runtime or security state."
        />
        <StatePanel
          title="No analysis history"
          description="Connect a project before running repository analysis."
          action={{ label: "Connect a project", href: "/dashboard/repositories" }}
        />
      </div>
    );
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Repository analysis"
        title="Saved analysis history"
        description="Chronological source-analysis records. Values shown here are saved analyzer output, not runtime measurements or independently verified security findings."
        actions={
          <Link
            href={`/dashboard/ai-analysis?project=${selectedProjectId}`}
            className="inline-flex min-h-11 items-center rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground shadow-sm hover:bg-surface-raised"
          >
            Back to latest result
          </Link>
        }
      />

      <ProjectSelector
        projects={projects}
        value={selectedProjectId}
        onChange={selectProject}
        className="block max-w-sm"
      />

      {selectedProject && <ProjectTabs projectId={selectedProject.id} />}

      {selectedProject && !loading && (
        <section aria-label="Analysis history context" className="rounded-xl border border-border bg-card px-4 py-4 shadow-sm sm:px-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-primary">Selected source record</p>
              <p className="mt-1 text-sm font-semibold text-foreground">{selectedProject.name}</p>
              <p className="mt-1 font-mono text-[11px] text-foreground-muted">{selectedProject.branch || "Branch not recorded"}</p>
            </div>
            <div className="rounded-lg border border-border bg-surface-subtle px-4 py-3 sm:text-right">
              <p className="text-xs text-foreground-muted">Saved runs</p>
              <p className="mt-1 font-mono text-xl font-semibold tabular-nums text-foreground">{analyses.length}</p>
            </div>
          </div>
        </section>
      )}

      {error ? (
        <StatePanel
          variant="error"
          title="Analysis history is unavailable"
          description={error}
          action={{ label: "Try again", onClick: () => void loadHistory(selectedProjectId) }}
        />
      ) : loading ? (
        <HistoryLoading compact />
      ) : analyses.length === 0 ? (
        <StatePanel
          title="No saved analyses"
          description="Run repository analysis to create the first durable result."
          action={{ label: "Open repository analysis", href: `/dashboard/ai-analysis?project=${selectedProjectId}` }}
        />
      ) : (
        <section className="space-y-3" aria-label="Saved repository analyses">
          {analyses.map((analysis, index) => {
            const expanded = expandedId === analysis.id;
            return (
              <article
                key={analysis.id}
                className={`overflow-hidden rounded-xl border bg-card shadow-sm transition-colors ${
                  index === 0 ? "border-primary/30" : "border-border"
                }`}
              >
                <button
                  type="button"
                  onClick={() => setExpandedId(expanded ? null : analysis.id)}
                  aria-expanded={expanded}
                  className="flex min-h-16 w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-subtle sm:px-5"
                >
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-primary-subtle text-primary">
                    <Clock3 size={16} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-foreground">
                        {analysis.framework || analysis.language || "Repository analysis"}
                      </span>
                      {index === 0 && (
                        <span className="rounded-full border border-primary/20 bg-primary-subtle px-2 py-0.5 text-[10px] font-semibold text-primary">
                          Latest
                        </span>
                      )}
                    </span>
                    <span className="mt-1 block text-[11px] text-foreground-muted">
                      {formatTimestamp(analysis.created_at)}
                    </span>
                  </span>
                  {expanded ? (
                    <ChevronUp size={16} className="text-foreground-muted" />
                  ) : (
                    <ChevronDown size={16} className="text-foreground-muted" />
                  )}
                </button>

                {expanded && (
                  <div className="space-y-5 border-t border-border px-4 py-5 sm:px-5">
                    <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                      {[
                        ["Framework", [analysis.framework, analysis.framework_version].filter(Boolean).join(" ")],
                        ["Language / runtime", analysis.runtime || analysis.language],
                        ["Package manager", analysis.package_manager],
                        ["Detected port", analysis.port],
                        ["CPU recommendation", analysis.cpu_recommendation],
                        ["Memory recommendation", analysis.memory_recommendation],
                        ["Storage recommendation", analysis.storage_recommendation],
                        ["Detected deployment shape", analysis.deployment_strategy],
                      ].map(([label, value]) => (
                        <div key={label} className="rounded-lg border border-border bg-surface-subtle p-3">
                          <dt className="text-[11px] font-medium text-foreground-muted">{label}</dt>
                          <dd className="mt-1 break-words font-mono text-xs text-foreground">
                            {value?.trim() || "Not recorded"}
                          </dd>
                        </div>
                      ))}
                    </dl>

                    <div className="grid gap-5 lg:grid-cols-2">
                      <div>
                        <h2 className="text-xs font-semibold text-foreground">Detected dependencies</h2>
                        {analysis.dependencies.length > 0 ? (
                          <ul className="mt-2 flex flex-wrap gap-2">
                            {analysis.dependencies.map((dependency) => (
                              <li key={dependency} className="rounded-md border border-border bg-surface-subtle px-2 py-1 font-mono text-[11px] text-foreground">
                                {dependency}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="mt-2 text-xs text-foreground-muted">None recorded.</p>
                        )}
                      </div>
                      <div>
                        <h2 className="text-xs font-semibold text-foreground">Analyzer warnings</h2>
                        {analysis.vulnerabilities.length > 0 ? (
                          <ul className="mt-2 space-y-2">
                            {analysis.vulnerabilities.map((warning, warningIndex) => (
                              <li key={`${warning}-${warningIndex}`} className="rounded-lg border border-warning/25 bg-warning-subtle px-3 py-2 text-xs leading-5 text-foreground">
                                {warning}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="mt-2 text-xs text-foreground-muted">
                            None recorded. This is not a clean bill of security.
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </section>
      )}
    </div>
  );
}

function HistoryLoading({ compact = false }: { compact?: boolean }) {
  return (
    <div
      role="status"
      className={`flex items-center justify-center gap-3 rounded-xl border border-border bg-card text-sm font-medium text-foreground-muted ${
        compact ? "min-h-52" : "min-h-[55vh]"
      }`}
    >
      <Loader2 size={18} className="animate-spin text-primary motion-reduce:animate-none" />
      Loading saved analysis history…
    </div>
  );
}
