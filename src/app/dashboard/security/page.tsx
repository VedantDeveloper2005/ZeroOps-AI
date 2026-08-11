"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  FileWarning,
  KeyRound,
  Loader2,
  LockKeyhole,
  RefreshCw,
  ScanSearch,
  ShieldCheck,
} from "lucide-react";
import { MetricCard } from "@/components/ui/MetricCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { ProjectSelector } from "@/components/dashboard/ProjectSelector";
import { ProjectTabs } from "@/components/dashboard/ProjectTabs";
import { useNotifications } from "@/lib/NotificationContext";
import {
  ApiError,
  api,
  getErrorMessage,
  type PipelineStageStatus,
  type SecurityScan,
  type SecurityStatus,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type ScanState = "idle" | "ready" | "no_record" | "unavailable" | "error";

function formatTimestamp(value: string | null | undefined) {
  if (!value) return "Time not recorded";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time not recorded" : date.toLocaleString();
}

function statusClasses(status: PipelineStageStatus) {
  if (status === "succeeded") return "border-success/25 bg-success-subtle text-success";
  if (status === "failed") return "border-danger/25 bg-danger-subtle text-danger";
  if (status === "blocked" || status === "unavailable") {
    return "border-warning/25 bg-warning-subtle text-warning";
  }
  if (status === "running") return "border-info/25 bg-info-subtle text-info";
  return "border-border bg-surface-subtle text-foreground-muted";
}

function statusLabel(status: PipelineStageStatus) {
  return status === "succeeded"
    ? "Passed"
    : status.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export default function SecurityPage() {
  return (
    <Suspense fallback={<SecurityPageLoading />}>
      <SecurityWorkspace />
    </Suspense>
  );
}

function SecurityWorkspace() {
  const searchParams = useSearchParams();
  const { projects, isLoading: projectsLoading } = useNotifications();
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [configuration, setConfiguration] = useState<SecurityStatus | null>(null);
  const [configurationError, setConfigurationError] = useState<string | null>(null);
  const [scans, setScans] = useState<SecurityScan[]>([]);
  const [scanState, setScanState] = useState<ScanState>("idle");
  const [scanError, setScanError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const requestSequence = useRef(0);

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

  const loadSecurity = useCallback(async (projectId: string) => {
    if (!projectId) return;
    const requestId = ++requestSequence.current;
    setLoading(true);
    setConfigurationError(null);
    setScanError(null);

    const [configurationResult, scansResult] = await Promise.allSettled([
      api.getSecurityStatus(projectId),
      api.getProjectSecurityScans(projectId),
    ]);

    if (requestId !== requestSequence.current) return;

    if (configurationResult.status === "fulfilled") {
      setConfiguration(configurationResult.value);
    } else {
      setConfiguration(null);
      setConfigurationError(
        getErrorMessage(configurationResult.reason, "Stored security controls could not be loaded."),
      );
    }

    if (scansResult.status === "fulfilled") {
      setScans(scansResult.value);
      setScanState(scansResult.value.length > 0 ? "ready" : "no_record");
    } else {
      setScans([]);
      const reason = scansResult.reason;
      if (reason instanceof ApiError && reason.status === 404) {
        setScanState("no_record");
      } else if (reason instanceof ApiError && reason.status === 503) {
        setScanState("unavailable");
        setScanError(getErrorMessage(reason, "A required security scanner is unavailable."));
      } else {
        setScanState("error");
        setScanError(getErrorMessage(reason, "Security scan history could not be loaded."));
      }
    }

    if (requestId === requestSequence.current) setLoading(false);
  }, []);

  useEffect(() => {
    void loadSecurity(selectedProjectId);
  }, [loadSecurity, selectedProjectId]);

  const latestScan = useMemo(
    () => [...scans].sort((first, second) => {
      const firstTime = new Date(first.completed_at || first.started_at || 0).getTime();
      const secondTime = new Date(second.completed_at || second.started_at || 0).getTime();
      return secondTime - firstTime;
    })[0] ?? null,
    [scans],
  );

  if (projectsLoading) return <SecurityPageLoading />;

  if (projects.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Project controls"
          title="Security evidence"
          description="Deterministic scanner results and stored controls; missing checks are never treated as passed."
        />
        <StatePanel
          title="No project security context"
          description="Connect a project before reviewing stored controls and deterministic scan results."
          action={{ label: "Connect a project", href: "/dashboard/repositories" }}
        />
      </div>
    );
  }

  if (!selectedProjectId) return <SecurityPageLoading />;

  const selectedProject = projects.find((project) => project.id === selectedProjectId);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Project controls"
        title="Security evidence"
        description="Deterministic scanner results and configuration ZeroOps can verify from stored records. Missing or unavailable checks are never treated as passed."
        actions={
          <button
            type="button"
            onClick={() => void loadSecurity(selectedProjectId)}
            disabled={loading || !selectedProjectId}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground shadow-sm transition-colors hover:bg-surface-raised disabled:opacity-50"
          >
            <RefreshCw size={15} className={loading ? "animate-spin motion-reduce:animate-none" : ""} aria-hidden="true" />
            Refresh
          </button>
        }
      />

      <section aria-label="Security context" className="rounded-xl border border-border bg-card p-4 shadow-sm sm:p-5">
        <ProjectSelector projects={projects} value={selectedProjectId} onChange={setSelectedProjectId} className="block w-full max-w-sm" />
        {selectedProject && (
          <div className="mt-5">
            <ProjectTabs projectId={selectedProject.id} />
          </div>
        )}
      </section>

      {loading ? (
        <SecurityLoading compact />
      ) : (
        <>
          <section aria-labelledby="latest-security-scan" className="space-y-4">
            <div className="flex items-start gap-3 rounded-xl border border-border bg-card px-4 py-4 shadow-sm sm:px-5">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-primary-subtle text-primary">
                <ScanSearch size={18} aria-hidden="true" />
              </span>
              <div>
              <h2 id="latest-security-scan" className="text-base font-semibold text-foreground">Latest deterministic scan</h2>
              <p className="mt-1 text-sm leading-6 text-foreground-muted">
                Source, dependency, secret, container, infrastructure, and Kubernetes checks appear only when the pipeline recorded them.
              </p>
              </div>
            </div>

            {scanState === "unavailable" ? (
              <StatePanel variant="disconnected" title="Security scanning unavailable" description={scanError || "A required scanner did not return a result. Deployment policy must fail closed where that check is required."} action={{ label: "Try again", onClick: () => void loadSecurity(selectedProjectId) }} />
            ) : scanState === "error" ? (
              <StatePanel variant="error" title="Security scan history could not be loaded" description={scanError || "The request failed."} action={{ label: "Try again", onClick: () => void loadSecurity(selectedProjectId) }} />
            ) : scanState === "no_record" || !latestScan ? (
              <StatePanel title="No security scan is recorded" description="No deterministic scan result exists for this project. This is not evidence that the source, dependencies, image, or infrastructure passed security checks." />
            ) : (
              <>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <MetricCard label="Policy result" value={latestScan.policy_result.replaceAll("_", " ")} supportingText="Recorded by the pipeline security policy" icon={ShieldCheck} tone={latestScan.policy_result === "passed" ? "success" : latestScan.policy_result === "blocked" ? "warning" : "neutral"} />
                  <MetricCard label="Blocking findings" value={latestScan.blocking_findings.toLocaleString()} supportingText="Findings that block under stored policy" icon={AlertTriangle} tone={latestScan.blocking_findings > 0 ? "warning" : "neutral"} />
                  <MetricCard label="Critical findings" value={(latestScan.finding_counts.critical ?? 0).toLocaleString()} supportingText="Recorded scanner severity" icon={FileWarning} tone={(latestScan.finding_counts.critical ?? 0) > 0 ? "warning" : "neutral"} />
                  <MetricCard label="Commit" value={latestScan.commit_sha?.slice(0, 8) || "Not recorded"} supportingText={formatTimestamp(latestScan.completed_at)} icon={ScanSearch} />
                </div>

                {latestScan.tools.length === 0 ? (
                  <StatePanel compact variant="info" title="No tool results were stored" description="The scan record contains an overall result but no per-tool evidence." />
                ) : (
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {latestScan.tools.map((tool, index) => (
                      <article key={`${tool.category}-${tool.tool}-${index}`} className="rounded-xl border border-border bg-card p-4 shadow-sm">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-xs font-semibold capitalize text-foreground-subtle">{tool.category.replaceAll("_", " ")}</p>
                            <h3 className="mt-1 text-sm font-semibold text-foreground">{tool.tool}</h3>
                          </div>
                          <span className={cn("rounded-full border px-2.5 py-1 text-xs font-semibold", statusClasses(tool.status))}>{statusLabel(tool.status)}</span>
                        </div>
                        <p className="mt-3 text-xs text-foreground-muted">{tool.finding_count} finding{tool.finding_count === 1 ? "" : "s"}; {tool.blocking_findings} blocking.</p>
                        {tool.reason && <p className="mt-2 rounded-lg bg-surface-subtle px-3 py-2 text-xs leading-5 text-foreground-muted">{tool.reason}</p>}
                      </article>
                    ))}
                  </div>
                )}

                <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
                  <div className="border-b border-border px-4 py-4 sm:px-5">
                    <h3 className="text-sm font-semibold text-foreground">Recorded findings</h3>
                    <p className="mt-1 text-xs text-foreground-muted">Secret values are never rendered; secret findings show metadata only.</p>
                  </div>
                  {latestScan.findings.length === 0 ? (
                    <p className="px-5 py-8 text-center text-xs text-foreground-muted">The completed scan stored no findings.</p>
                  ) : (
                    <ul className="divide-y divide-border">
                      {latestScan.findings.slice(0, 20).map((finding) => (
                        <li key={finding.id} className="px-4 py-4 sm:px-5">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-xs font-semibold text-foreground">{finding.title}</span>
                            <span className="rounded-full border border-border bg-surface-subtle px-2.5 py-1 text-xs font-semibold capitalize text-foreground-muted">{finding.severity}</span>
                            {finding.blocking && <span className="rounded-full border border-danger/25 bg-danger-subtle px-2.5 py-1 text-xs font-semibold text-danger">Blocking</span>}
                          </div>
                          <p className="mt-1 text-xs text-foreground-muted">{finding.scanner}{finding.rule_id ? ` · ${finding.rule_id}` : ""}{finding.file_path ? ` · ${finding.file_path}${finding.line_number ? `:${finding.line_number}` : ""}` : ""}</p>
                          {!latestScan.tools.some((tool) => tool.category === "secret") && finding.description && <p className="mt-2 text-xs leading-5 text-foreground-muted">{finding.description}</p>}
                          {latestScan.tools.some((tool) => tool.category === "secret") && <p className="mt-2 text-xs text-foreground-muted">Potential secret content redacted.</p>}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </>
            )}
          </section>

          <section aria-labelledby="stored-security-controls" className="rounded-xl border border-border bg-card p-5 shadow-sm">
            <div className="flex items-center gap-2">
              <KeyRound size={17} className="text-primary" aria-hidden="true" />
              <h2 id="stored-security-controls" className="text-base font-semibold text-foreground">Stored identity and secret controls</h2>
            </div>
            {configurationError ? (
              <div className="mt-4">
                <StatePanel compact variant="error" title="Stored controls unavailable" description={configurationError} />
              </div>
            ) : configuration ? (
              <dl className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {[
                  ["Secret records", configuration.secretsManaged.toLocaleString()],
                  ["HTTPS metadata", configuration.httpsStatus || "Not configured"],
                  ["Namespace isolation", configuration.namespaceIsolated ? "Recorded as enabled" : "Not recorded"],
                  ["Role-based access", configuration.rbacEnabled ? "Recorded as enabled" : "Not recorded"],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg border border-border bg-surface-subtle px-3 py-3">
                    <dt className="text-xs font-medium text-foreground-subtle">{label}</dt>
                    <dd className="mt-1.5 text-sm font-semibold text-foreground">{value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="mt-4 text-xs text-foreground-muted">No control record was returned.</p>
            )}
            <div className="mt-4 flex items-start gap-2 rounded-lg border border-info/25 bg-info-subtle px-3 py-2.5 text-xs leading-5 text-foreground-muted">
              <LockKeyhole size={15} className="mt-0.5 shrink-0 text-info" aria-hidden="true" />
              These records do not certify SOC 2 compliance, guarantee security, or prove that no attack occurred.
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function SecurityLoading({ compact = false }: { compact?: boolean }) {
  return (
    <div role="status" className={`flex items-center justify-center gap-3 rounded-xl border border-border bg-card text-sm font-medium text-foreground-muted ${compact ? "min-h-52" : "min-h-[55vh]"}`}>
      <Loader2 size={18} className="animate-spin text-primary motion-reduce:animate-none" aria-hidden="true" />
      Loading security evidence…
    </div>
  );
}

function SecurityPageLoading() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Project controls"
        title="Security evidence"
        description="Deterministic scanner results and stored controls; missing checks are never treated as passed."
      />
      <SecurityLoading />
    </div>
  );
}
