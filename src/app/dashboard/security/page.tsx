"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  FileWarning,
  KeyRound,
  Loader2,
  LockKeyhole,
  RefreshCw,
  ServerCog,
  ShieldCheck,
} from "lucide-react";
import { MetricCard } from "@/components/ui/MetricCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { ProjectSelector } from "@/components/dashboard/ProjectSelector";
import { ProjectTabs } from "@/components/dashboard/ProjectTabs";
import { useNotifications } from "@/lib/NotificationContext";
import { api, getErrorMessage, type SecurityStatus } from "@/lib/api";

export default function SecurityPage() {
  return (
    <Suspense fallback={<SecurityLoading />}>
      <SecurityWorkspace />
    </Suspense>
  );
}

function SecurityWorkspace() {
  const searchParams = useSearchParams();
  const { projects, isLoading: projectsLoading } = useNotifications();
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [status, setStatus] = useState<SecurityStatus | null>(null);
  const [loading, setLoading] = useState(false);
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

  const loadStatus = useCallback(async (projectId: string) => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      setStatus(await api.getSecurityStatus(projectId));
    } catch (requestError) {
      setStatus(null);
      setError(getErrorMessage(requestError, "Security configuration could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStatus(selectedProjectId);
  }, [loadStatus, selectedProjectId]);

  if (projectsLoading) return <SecurityLoading />;

  if (projects.length === 0) {
    return (
      <StatePanel
        title="No project security context"
        description="Connect a project before reviewing stored secrets, HTTPS metadata, and analysis warnings."
        action={{ label: "Connect a project", href: "/dashboard/repositories" }}
      />
    );
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Project controls"
        title="Security configuration"
        description="A factual view of configuration ZeroOps can verify from its own records. Active threat detection, firewall telemetry, compliance certification, and independent CVE scanning are not connected."
        actions={
          <button
            type="button"
            onClick={() => void loadStatus(selectedProjectId)}
            disabled={loading || !selectedProjectId}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground shadow-sm transition-colors hover:bg-surface-raised disabled:opacity-50"
          >
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        }
      />

      <ProjectSelector
        projects={projects}
        value={selectedProjectId}
        onChange={setSelectedProjectId}
        className="block max-w-sm"
      />

      {selectedProject && <ProjectTabs projectId={selectedProject.id} />}

      {error ? (
        <StatePanel
          variant="error"
          title="Security configuration is unavailable"
          description={error}
          action={{ label: "Try again", onClick: () => void loadStatus(selectedProjectId) }}
        />
      ) : loading ? (
        <SecurityLoading compact />
      ) : status ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Stored secrets"
              value={status.secretsManaged.toLocaleString()}
              supportingText="Secret records associated with this project"
              icon={KeyRound}
              tone={status.secretsManaged > 0 ? "success" : "neutral"}
            />
            <MetricCard
              label="HTTPS metadata"
              value={status.httpsStatus || "Not configured"}
              supportingText="External certificate validation is not connected"
              icon={LockKeyhole}
              tone={status.httpsStatus === "Active" ? "success" : "neutral"}
            />
            <MetricCard
              label="Analyzer warnings"
              value={status.vulnerabilities.toLocaleString()}
              supportingText="Latest saved repository-analysis warnings; not verified CVEs"
              icon={FileWarning}
              tone={status.vulnerabilities > 0 ? "warning" : "neutral"}
            />
            <MetricCard
              label="Firewall telemetry"
              value={status.firewallStatus || "Unavailable"}
              supportingText="No firewall event feed is connected"
              icon={ServerCog}
            />
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
              <div className="flex items-center gap-2">
                <ShieldCheck size={17} className="text-primary" />
                <h2 className="text-sm font-semibold text-foreground">Recorded controls</h2>
              </div>
              <dl className="mt-4 divide-y divide-border rounded-lg border border-border">
                {[
                  ["HTTPS configuration", status.httpsStatus || "Not configured"],
                  ["Secret records", `${status.secretsManaged}`],
                  ["Namespace isolation", status.namespaceIsolated ? "Recorded as enabled" : "Not recorded"],
                  ["Role-based access", status.rbacEnabled ? "Recorded as enabled" : "Not recorded"],
                ].map(([label, value]) => (
                  <div key={label} className="flex items-start justify-between gap-4 px-4 py-3">
                    <dt className="text-xs text-foreground-muted">{label}</dt>
                    <dd className="text-right text-xs font-semibold text-foreground">{value}</dd>
                  </div>
                ))}
              </dl>
            </section>

            <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
              <div className="flex items-center gap-2">
                <FileWarning size={17} className="text-warning" />
                <h2 className="text-sm font-semibold text-foreground">Assessment boundaries</h2>
              </div>
              <ul className="mt-4 space-y-3 text-xs leading-5 text-foreground-muted">
                <li className="rounded-lg border border-border bg-surface-subtle px-3 py-2.5">
                  Compliance status: <strong className="font-semibold text-foreground">{status.soc2Status || "Not assessed"}</strong>. ZeroOps does not certify SOC 2 compliance.
                </li>
                <li className="rounded-lg border border-border bg-surface-subtle px-3 py-2.5">
                  No blocked-IP or attack-event feed is connected, so an empty event list would not prove that no attacks occurred.
                </li>
                <li className="rounded-lg border border-border bg-surface-subtle px-3 py-2.5">
                  Repository analysis can flag configuration concerns but does not replace a dependency, image, or cloud-security scanner.
                </li>
              </ul>
            </section>
          </div>
        </>
      ) : (
        <StatePanel
          variant="empty"
          title="No security status was returned"
          description="ZeroOps did not receive a security configuration record for this project."
        />
      )}
    </div>
  );
}

function SecurityLoading({ compact = false }: { compact?: boolean }) {
  return (
    <div
      role="status"
      className={`flex items-center justify-center gap-3 rounded-xl border border-border bg-card text-sm font-medium text-foreground-muted ${
        compact ? "min-h-52" : "min-h-[55vh]"
      }`}
    >
      <Loader2 size={18} className="animate-spin text-primary" />
      Loading security configuration…
    </div>
  );
}
