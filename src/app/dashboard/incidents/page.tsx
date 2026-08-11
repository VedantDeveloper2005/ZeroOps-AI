"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  BrainCircuit,
  Check,
  ChevronDown,
  Copy,
  Loader2,
  Play,
  RefreshCw,
  ShieldAlert,
  X,
} from "lucide-react";
import { ProjectSelector } from "@/components/dashboard/ProjectSelector";
import { ProjectTabs } from "@/components/dashboard/ProjectTabs";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { useNotifications } from "@/lib/NotificationContext";
import {
  ApiError,
  api,
  getErrorMessage,
  type Incident,
  type RemediationProposal,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type IncidentResponseState = "idle" | "ready" | "no_record" | "unavailable" | "error";

function formatTimestamp(value: string | null | undefined) {
  if (!value) return "Time not recorded";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time not recorded" : date.toLocaleString();
}

function severityClasses(severity: Incident["severity"]) {
  if (severity === "critical") return "border-danger/25 bg-danger-subtle text-danger";
  if (severity === "high") return "border-warning/30 bg-warning-subtle text-warning";
  if (severity === "medium") return "border-info/25 bg-info-subtle text-info";
  return "border-border bg-surface-subtle text-foreground-muted";
}

function remediationClasses(risk: RemediationProposal["risk"]) {
  if (risk === "high") return "border-danger/25 bg-danger-subtle text-danger";
  if (risk === "medium") return "border-warning/25 bg-warning-subtle text-warning";
  return "border-info/25 bg-info-subtle text-info";
}

function severityBorderClass(severity: Incident["severity"]) {
  if (severity === "critical") return "border-l-danger";
  if (severity === "high") return "border-l-warning";
  if (severity === "medium") return "border-l-info";
  return "border-l-border-hover";
}

export default function IncidentsPage() {
  return (
    <Suspense fallback={<IncidentsPageLoading />}>
      <IncidentsWorkspace />
    </Suspense>
  );
}

function IncidentsWorkspace() {
  const searchParams = useSearchParams();
  const { addToast, projects, isLoading: projectsLoading } = useNotifications();
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [state, setState] = useState<IncidentResponseState>("idle");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
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

  const loadIncidents = useCallback(async (projectId: string) => {
    if (!projectId) return;
    const requestId = ++requestSequence.current;
    setLoading(true);
    setError(null);
    try {
      const records = await api.getProjectIncidents(projectId);
      if (requestId !== requestSequence.current) return;
      setIncidents(records);
      setState(records.length > 0 ? "ready" : "no_record");
    } catch (requestError) {
      if (requestId !== requestSequence.current) return;
      setIncidents([]);
      if (requestError instanceof ApiError && requestError.status === 404) {
        setState("no_record");
      } else if (requestError instanceof ApiError && requestError.status === 503) {
        setState("unavailable");
        setError(getErrorMessage(requestError, "Incident detection is unavailable."));
      } else {
        setState("error");
        setError(getErrorMessage(requestError, "Incident records could not be loaded."));
      }
    } finally {
      if (requestId === requestSequence.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadIncidents(selectedProjectId);
  }, [loadIncidents, selectedProjectId]);

  function replaceIncident(updated: Incident) {
    setIncidents((current) => current.map((incident) => incident.id === updated.id ? updated : incident));
  }

  function replaceProposal(incidentId: string, updated: RemediationProposal) {
    setIncidents((current) =>
      current.map((incident) =>
        incident.id === incidentId
          ? {
              ...incident,
              remediation_proposals: (incident.remediation_proposals ?? []).map((proposal) =>
                proposal.id === updated.id ? updated : proposal,
              ),
            }
          : incident,
      ),
    );
  }

  async function acknowledge(incident: Incident) {
    setPendingAction(`acknowledge:${incident.id}`);
    try {
      replaceIncident(await api.acknowledgeIncident(incident.id));
      addToast(`${incident.id} was acknowledged.`, "success");
    } catch (requestError) {
      addToast(getErrorMessage(requestError, "The incident could not be acknowledged."), "error");
    } finally {
      setPendingAction(null);
    }
  }

  async function dismiss(incident: Incident) {
    if (!window.confirm(`Dismiss ${incident.id}? This records a dismissal; it does not verify service recovery.`)) return;
    setPendingAction(`dismiss:${incident.id}`);
    try {
      replaceIncident(await api.dismissIncident(incident.id));
      addToast(`${incident.id} was dismissed.`, "success");
    } catch (requestError) {
      addToast(getErrorMessage(requestError, "The incident could not be dismissed."), "error");
    } finally {
      setPendingAction(null);
    }
  }

  async function investigate(incident: Incident) {
    setPendingAction(`investigate:${incident.id}`);
    try {
      const investigation = await api.requestIncidentInvestigation(incident.id);
      setIncidents((current) => current.map((item) => item.id === incident.id ? { ...item, investigation } : item));
      addToast(
        investigation.status === "unavailable"
          ? investigation.unavailable_reason || "A durable incident-investigation worker is not available."
          : `The investigation is ${investigation.status}.`,
        investigation.status === "unavailable" ? "error" : "success",
      );
    } catch (requestError) {
      addToast(getErrorMessage(requestError, "The investigation could not be requested."), "error");
    } finally {
      setPendingAction(null);
    }
  }

  async function decideProposal(incident: Incident, proposal: RemediationProposal, decision: "approve" | "reject") {
    const decisionText = decision === "approve" ? "approve" : "reject";
    if (!window.confirm(`${decisionText[0].toUpperCase()}${decisionText.slice(1)} “${proposal.title}” (${proposal.risk} risk)?`)) return;
    setPendingAction(`${decision}:${proposal.id}`);
    try {
      const updated = decision === "approve"
        ? await api.approveRemediationProposal(proposal.id)
        : await api.rejectRemediationProposal(proposal.id);
      replaceProposal(incident.id, updated);
      addToast(`Remediation proposal ${decision === "approve" ? "approved" : "rejected"}.`, "success");
    } catch (requestError) {
      addToast(
        getErrorMessage(
          requestError,
          `The remediation proposal could not be ${decision === "approve" ? "approved" : "rejected"}.`,
        ),
        "error",
      );
    } finally {
      setPendingAction(null);
    }
  }

  async function executeProposal(incident: Incident, proposal: RemediationProposal) {
    if (!window.confirm(`Execute “${proposal.title}”? The backend will enforce the stored approval and risk policy.`)) return;
    setPendingAction(`execute:${proposal.id}`);
    try {
      const execution = await api.executeRemediationProposal(proposal.id);
      const proposalStatus =
        execution.status === "queued"
          ? "execution_queued"
          : execution.status === "running"
            ? "executing"
            : execution.status === "succeeded"
              ? "executed"
              : execution.status;
      replaceProposal(incident.id, { ...proposal, status: proposalStatus });
      addToast(
        execution.error ||
          `The remediation execution is ${execution.status}. Completion is not assumed unless verification succeeds.`,
        execution.status === "failed" ||
          execution.status === "cancelled" ||
          execution.status === "unavailable"
          ? "error"
          : "success",
      );
    } catch (requestError) {
      addToast(getErrorMessage(requestError, "The remediation could not be queued."), "error");
    } finally {
      setPendingAction(null);
    }
  }

  async function copyIncident(incident: Incident) {
    const report = [
      "ZEROOPS INCIDENT",
      `Incident: ${incident.id}`,
      `Detected: ${formatTimestamp(incident.detected_at)}`,
      `Severity: ${incident.severity}`,
      `Status: ${incident.status}`,
      `Rule: ${incident.rule}`,
      `Deployment: ${incident.deployment_revision || incident.deployment_id || "Not recorded"}`,
      "",
      incident.title,
      incident.summary,
    ].join("\n");
    try {
      await navigator.clipboard.writeText(report);
      addToast("Incident summary copied.", "success");
    } catch {
      addToast("Clipboard access was not available.", "error");
    }
  }

  if (projectsLoading) return <IncidentsPageLoading />;

  if (projects.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Operations"
          title="Incidents"
          description="Deterministic anomaly records and controlled remediation from the incident API."
        />
        <StatePanel title="No project incident context" description="Connect a project before reviewing detected runtime incidents." action={{ label: "Connect a project", href: "/dashboard/repositories" }} />
      </div>
    );
  }

  if (!selectedProjectId) return <IncidentsPageLoading />;

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const openCount = incidents.filter((incident) => !["resolved", "dismissed"].includes(incident.status)).length;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="Incidents"
        description="Deterministic anomaly records, saved evidence, investigations, and controlled remediation. Actions are shown only when backed by the incident API."
        actions={
          <button type="button" onClick={() => void loadIncidents(selectedProjectId)} disabled={loading || !selectedProjectId} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground shadow-sm hover:bg-surface-raised disabled:opacity-50">
            <RefreshCw size={15} className={loading ? "animate-spin motion-reduce:animate-none" : ""} aria-hidden="true" /> Refresh
          </button>
        }
      />

      <section aria-label="Incident context" className="rounded-xl border border-border bg-card p-4 shadow-sm sm:p-5">
        <ProjectSelector projects={projects} value={selectedProjectId} onChange={setSelectedProjectId} className="block w-full max-w-sm" />
        {selectedProject && (
          <div className="mt-5">
            <ProjectTabs projectId={selectedProject.id} />
          </div>
        )}
      </section>

      {!loading && state === "ready" && (
        <div role="status" className="grid overflow-hidden rounded-xl border border-info/25 bg-card sm:grid-cols-[auto_1fr]">
          <div className="flex items-center gap-3 bg-info-subtle px-5 py-4">
            <ShieldAlert size={18} className="text-info" aria-hidden="true" />
            <div>
              <p className="font-mono text-xl font-semibold text-foreground tabular-nums">{openCount}</p>
              <p className="text-xs font-medium text-foreground-muted">Open or active</p>
            </div>
          </div>
          <p className="flex items-center border-t border-border px-5 py-4 text-sm leading-6 text-foreground-muted sm:border-l sm:border-t-0">
            Acknowledgement and dismissal update the record; neither action verifies service recovery.
          </p>
        </div>
      )}

      {loading ? (
        <IncidentsLoading compact />
      ) : state === "unavailable" ? (
        <StatePanel variant="disconnected" title="Incident detection unavailable" description={error || "The incident service did not return a result. An empty list is not being shown."} action={{ label: "Try again", onClick: () => void loadIncidents(selectedProjectId) }} />
      ) : state === "error" ? (
        <StatePanel variant="error" title="Incident records could not be loaded" description={error || "The request failed."} action={{ label: "Try again", onClick: () => void loadIncidents(selectedProjectId) }} />
      ) : state === "no_record" ? (
        <StatePanel title="No incidents are recorded" description="The incident API returned no records for this project. This does not prove the deployed service had no incidents." />
      ) : (
        <section aria-label="Recorded incidents" className="space-y-4">
          {incidents.map((incident) => {
            const investigation = incident.investigation;
            const proposals = incident.remediation_proposals ?? [];
            return (
              <article key={incident.id} className={cn("overflow-hidden rounded-xl border border-l-4 border-border bg-card shadow-sm", severityBorderClass(incident.severity))}>
                <div className="border-b border-border p-4 sm:p-5">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <AlertTriangle size={16} className={incident.severity === "critical" ? "text-danger" : "text-warning"} aria-hidden="true" />
                        <span className="font-mono text-xs font-semibold text-foreground">{incident.id}</span>
                        <span className={cn("rounded-full border px-2.5 py-1 text-xs font-semibold capitalize", severityClasses(incident.severity))}>{incident.severity}</span>
                        <span className="rounded-full border border-border bg-surface-subtle px-2.5 py-1 text-xs font-semibold capitalize text-foreground-muted">{incident.status.replaceAll("_", " ")}</span>
                      </div>
                      <h2 className="mt-3 text-lg font-semibold tracking-[-0.02em] text-foreground">{incident.title}</h2>
                      <p className="mt-1 max-w-3xl text-sm leading-6 text-foreground-muted">{incident.summary}</p>
                      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-foreground-subtle">
                        <span>Detected: {formatTimestamp(incident.detected_at)}</span>
                        <span>Rule: {incident.rule}</span>
                        <span>Deployment: {incident.deployment_revision || incident.deployment_id || "Not recorded"}</span>
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-wrap gap-2">
                      {!incident.acknowledged_at && !["resolved", "dismissed"].includes(incident.status) && (
                        <button type="button" onClick={() => void acknowledge(incident)} disabled={pendingAction !== null} className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-border px-3 text-xs font-semibold text-foreground transition-colors hover:bg-surface-raised disabled:opacity-50"><Check size={14} aria-hidden="true" /> Acknowledge</button>
                      )}
                      {!investigation && !["resolved", "dismissed"].includes(incident.status) && (
                        <button type="button" onClick={() => void investigate(incident)} disabled={pendingAction !== null} className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-primary/25 bg-primary-subtle px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/10 disabled:opacity-50"><BrainCircuit size={14} aria-hidden="true" /> Request investigation</button>
                      )}
                      {!["resolved", "dismissed"].includes(incident.status) && (
                        <button type="button" onClick={() => void dismiss(incident)} disabled={pendingAction !== null} className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-border px-3 text-xs font-semibold text-foreground transition-colors hover:bg-surface-raised disabled:opacity-50"><X size={14} aria-hidden="true" /> Dismiss</button>
                      )}
                      <button type="button" onClick={() => void copyIncident(incident)} className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-border px-3 text-xs font-semibold text-foreground transition-colors hover:bg-surface-raised"><Copy size={14} aria-hidden="true" /> Copy</button>
                    </div>
                  </div>
                </div>

                <details className="group">
                  <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-xs font-semibold text-foreground transition-colors hover:bg-surface-subtle sm:px-5 [&::-webkit-details-marker]:hidden">
                    <span>Evidence and investigation</span>
                    <span className="flex items-center gap-2 text-foreground-subtle">
                      {incident.evidence.length} evidence {incident.evidence.length === 1 ? "item" : "items"}
                      <ChevronDown size={15} className="transition-transform group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
                    </span>
                  </summary>
                <div className="grid gap-4 border-t border-border p-4 sm:p-5 lg:grid-cols-2">
                  <section className="rounded-lg border border-border bg-surface-subtle p-4">
                    <div className="flex items-center gap-2"><ShieldAlert size={15} className="text-warning" aria-hidden="true" /><h3 className="text-xs font-semibold text-foreground">Evidence</h3></div>
                    {incident.evidence.length === 0 ? (
                      <p className="mt-3 text-xs text-foreground-muted">No evidence entries were stored.</p>
                    ) : (
                      <ul className="mt-3 space-y-2">
                        {incident.evidence.map((evidence, index) => (
                          <li key={evidence.id ?? `${evidence.source}-${index}`} className="rounded-lg border border-border bg-card px-3 py-2.5">
                            <p className="text-xs font-semibold capitalize text-foreground-subtle">{evidence.source.replaceAll("_", " ")}</p>
                            <p className="mt-1 text-xs leading-5 text-foreground-muted">{evidence.summary}</p>
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>

                  <section className="rounded-lg border border-border bg-surface-subtle p-4">
                    <div className="flex items-center gap-2"><BrainCircuit size={15} className="text-primary" aria-hidden="true" /><h3 className="text-xs font-semibold text-foreground">AI investigation</h3></div>
                    {!investigation ? (
                      <p className="mt-3 text-xs text-foreground-muted">No investigation is recorded. AI analysis has not been assumed.</p>
                    ) : (
                      <div className="mt-3 space-y-3 text-xs">
                        <p className="rounded-lg border border-border bg-card px-3 py-2 font-semibold text-foreground">Status: {investigation.status}</p>
                        {investigation.status === "unavailable" && (
                          <p className="rounded-lg border border-warning/25 bg-warning-subtle px-3 py-2 leading-5 text-foreground-muted">
                            {investigation.unavailable_reason || "The investigation service did not provide a diagnosis."}
                          </p>
                        )}
                        <div><p className="text-xs font-semibold text-foreground-subtle">Probable root cause</p><p className="mt-1 leading-5 text-foreground-muted">{investigation.probable_root_cause || "Not recorded"}</p></div>
                        <div><p className="text-xs font-semibold text-foreground-subtle">Recommended fix</p><p className="mt-1 leading-5 text-foreground-muted">{investigation.recommended_fix || "Not recorded"}</p></div>
                        <p className="text-xs text-foreground-subtle">Confidence: {investigation.confidence == null ? "Not recorded" : `${Math.round(investigation.confidence * (investigation.confidence <= 1 ? 100 : 1))}%`} · Sanitized context: {investigation.sanitized_context ? "recorded as yes" : "not confirmed"}</p>
                      </div>
                    )}
                  </section>
                </div>
                </details>

                <details className="group border-t border-border">
                  <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-xs font-semibold text-foreground transition-colors hover:bg-surface-subtle sm:px-5 [&::-webkit-details-marker]:hidden">
                    Remediation proposals ({proposals.length})
                    <ChevronDown size={15} className="transition-transform group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
                  </summary>
                  <div className="grid gap-3 border-t border-border bg-surface-subtle p-4 sm:p-5">
                    {proposals.length === 0 ? (
                      <p className="text-xs text-foreground-muted">No remediation proposal is stored. ZeroOps has not implied that an action is available.</p>
                    ) : proposals.map((proposal) => (
                      <article key={proposal.id} className="rounded-lg border border-border bg-card p-4">
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                          <div>
                            <div className="flex flex-wrap items-center gap-2">
                              <h4 className="text-xs font-semibold text-foreground">{proposal.title}</h4>
                              <span className={cn("rounded-full border px-2.5 py-1 text-xs font-semibold capitalize", remediationClasses(proposal.risk))}>{proposal.risk} risk</span>
                              <span className="rounded-full border border-border bg-surface-subtle px-2.5 py-1 text-xs font-semibold capitalize text-foreground-muted">{proposal.status}</span>
                            </div>
                            <p className="mt-2 text-xs leading-5 text-foreground-muted">{proposal.description}</p>
                            <p className="mt-2 text-xs text-foreground-subtle">Action: {proposal.action_type} · Approval: {proposal.requires_approval ? "required" : "not required by recorded policy"}</p>
                          </div>
                          <div className="flex shrink-0 flex-wrap gap-2">
                            {proposal.status === "proposed" && (
                              <>
                                <button type="button" onClick={() => void decideProposal(incident, proposal, "approve")} disabled={pendingAction !== null} className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-primary/25 bg-primary-subtle px-3 text-xs font-semibold text-primary disabled:opacity-50"><Check size={14} aria-hidden="true" /> Approve</button>
                                <button type="button" onClick={() => void decideProposal(incident, proposal, "reject")} disabled={pendingAction !== null} className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-border px-3 text-xs font-semibold text-foreground disabled:opacity-50"><X size={14} aria-hidden="true" /> Reject</button>
                              </>
                            )}
                            {proposal.status === "approved" && (
                              <button type="button" onClick={() => void executeProposal(incident, proposal)} disabled={pendingAction !== null} className="inline-flex min-h-11 items-center gap-1.5 rounded-lg bg-primary px-3 text-xs font-semibold text-primary-foreground disabled:opacity-50"><Play size={14} aria-hidden="true" /> Execute approved action</button>
                            )}
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                </details>
              </article>
            );
          })}
        </section>
      )}
    </div>
  );
}

function IncidentsLoading({ compact = false }: { compact?: boolean }) {
  return (
    <div role="status" className={`flex items-center justify-center gap-3 rounded-xl border border-border bg-card text-sm text-foreground-muted ${compact ? "min-h-52" : "min-h-[55vh]"}`}>
      <Loader2 size={18} className="animate-spin text-primary motion-reduce:animate-none" aria-hidden="true" />
      Loading incident records…
    </div>
  );
}

function IncidentsPageLoading() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="Incidents"
        description="Deterministic anomaly records and controlled remediation from the incident API."
      />
      <IncidentsLoading />
    </div>
  );
}
