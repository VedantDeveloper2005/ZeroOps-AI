"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Check,
  Loader2,
  RefreshCw,
  Save,
  ShieldCheck,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { ProjectSelector } from "@/components/dashboard/ProjectSelector";
import { ProjectTabs } from "@/components/dashboard/ProjectTabs";
import { useNotifications } from "@/lib/NotificationContext";
import { useProjectSelection } from "@/lib/useProjectSelection";
import {
  ApiError,
  api,
  getErrorMessage,
  type PipelineConfiguration,
  type PipelineConfigurationUpdate,
  type PipelineDeploymentMode,
} from "@/lib/api";

type LoadState = "idle" | "ready" | "no_record" | "error";

function formatTimestamp(value: string | null | undefined) {
  if (!value) return "Never";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Never" : date.toLocaleString();
}

function Toggle({
  id,
  label,
  description,
  checked,
  onChange,
  disabled,
}: {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-xl border border-border bg-background px-4 py-3.5 transition-colors hover:border-border-hover">
      <div className="min-w-0">
        <label htmlFor={id} className="text-sm font-medium text-foreground cursor-pointer">
          {label}
        </label>
        <p className="mt-1 text-xs leading-5 text-foreground-muted">{description}</p>
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={[
          "relative mt-0.5 inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50",
          checked ? "bg-primary" : "bg-border-hover",
        ].join(" ")}
      >
        <span
          className={[
            "pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow ring-0 transition-transform duration-200",
            checked ? "translate-x-5" : "translate-x-0",
          ].join(" ")}
        />
      </button>
    </div>
  );
}

export default function PipelineSettingsPage() {
  return (
    <Suspense fallback={<PipelineSettingsLoading />}>
      <PipelineSettingsWorkspace />
    </Suspense>
  );
}

function PipelineSettingsLoading() {
  return (
    <div className="flex h-64 items-center justify-center">
      <Loader2 size={24} className="animate-spin text-foreground-subtle" />
    </div>
  );
}

function PipelineSettingsWorkspace() {
  const searchParams = useSearchParams();
  const { projects, projectsState, refreshProjects, isLoading: projectsLoading } = useNotifications();
  const [selectedProjectId, setSelectedProjectId] = useProjectSelection(projects, searchParams.get("project"));
  const [config, setConfig] = useState<PipelineConfiguration | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const requestSequence = useRef(0);

  // Draft state for edits
  const [draft, setDraft] = useState<PipelineConfigurationUpdate | null>(null);
  const isDirty = draft !== null && config !== null && JSON.stringify(toUpdate(config)) !== JSON.stringify(draft);

  const loadConfiguration = useCallback(async () => {
    if (!selectedProjectId) return;
    const seq = ++requestSequence.current;
    setLoadState("idle");
    setLoadError(null);
    setConfig(null);
    setDraft(null);
    setSaveError(null);
    setSaveSuccess(false);

    try {
      const result = await api.getPipelineConfiguration(selectedProjectId);
      if (seq !== requestSequence.current) return;
      setConfig(result);
      setDraft(toUpdate(result));
      setLoadState("ready");
    } catch (error) {
      if (seq !== requestSequence.current) return;
      if (error instanceof ApiError && error.status === 404) {
        setLoadState("no_record");
      } else {
        setLoadError(getErrorMessage(error, "Pipeline configuration could not be loaded."));
        setLoadState("error");
      }
    }
  }, [selectedProjectId]);

  useEffect(() => {
    loadConfiguration();
    return () => { requestSequence.current += 1; };
  }, [loadConfiguration]);

  async function handleSave() {
    if (!selectedProjectId || !draft || saving) return;
    const seq = requestSequence.current;
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(false);

    try {
      const result = await api.updatePipelineConfiguration(selectedProjectId, draft);
      if (seq !== requestSequence.current) return;
      setConfig(result);
      setDraft(toUpdate(result));
      setSaveSuccess(true);
      setTimeout(() => {
        if (seq === requestSequence.current) setSaveSuccess(false);
      }, 3000);
    } catch (error) {
      if (seq !== requestSequence.current) return;
      setSaveError(getErrorMessage(error, "Pipeline configuration could not be saved."));
    } finally {
      setSaving(false);
    }
  }

  function updateDraft<K extends keyof PipelineConfigurationUpdate>(
    key: K,
    value: PipelineConfigurationUpdate[K],
  ) {
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));
    setSaveSuccess(false);
    setSaveError(null);
  }

  if (projectsLoading) return <PipelineSettingsLoading />;

  if (projectsState === "error") {
    return <StatePanel variant="error" title="Projects unavailable" description="Your projects could not be loaded." action={{ label: "Try again", onClick: () => void refreshProjects() }} />;
  }

  if (projects.length === 0) {
    return <StatePanel title="No projects yet" description="Connect a repository or upload your code before configuring its pipeline." action={{ label: "Create project", href: "/dashboard/repositories" }} />;
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6">
      <PageHeader
        eyebrow="Settings"
        title="Pipeline Configuration"
        description="Configure the DevSecOps pipeline behavior for each project."
      />

      {selectedProjectId && <ProjectTabs projectId={selectedProjectId} />}

      <div className="flex items-center justify-between gap-4">
        <ProjectSelector
          projects={projects}
          value={selectedProjectId}
          onChange={setSelectedProjectId}
        />
        <button
          type="button"
          onClick={loadConfiguration}
          disabled={!selectedProjectId}
          className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground transition-colors hover:border-border-hover hover:bg-surface-subtle disabled:opacity-50"
        >
          <RefreshCw aria-hidden="true" size={13} />
          Refresh
        </button>
      </div>

      {loadState === "idle" ? (
        <div className="flex h-40 items-center justify-center">
          <Loader2 size={20} className="animate-spin text-foreground-subtle" />
        </div>
      ) : loadState === "error" ? (
        <StatePanel
          title="Configuration unavailable"
          description={loadError || "Could not load pipeline configuration."}
          variant="error"
        />
      ) : loadState === "no_record" ? (
        <StatePanel
          title="No configuration found"
          description="This project does not have a pipeline configuration yet. A configuration will be created when the first pipeline run is triggered."
          variant="info"
        />
      ) : config && draft ? (
        <div className="space-y-6">
          {/* Meta information */}
          <div className="flex items-center justify-between rounded-xl border border-border bg-card px-4 py-3 text-xs text-foreground-muted">
            <span>Last updated: {formatTimestamp(config.updated_at)}</span>
            <span className="flex items-center gap-1.5">
              <ShieldCheck aria-hidden="true" size={13} className="text-primary" />
              {config.github_webhook_secret_configured
                ? "Webhook secret configured"
                : "No webhook secret"}
            </span>
          </div>

          {/* General settings */}
          <section>
            <h3 className="mb-3 text-sm font-semibold text-foreground">General</h3>
            <div className="space-y-2">
              <div className="rounded-xl border border-border bg-background px-4 py-3.5">
                <label htmlFor="branch" className="block text-sm font-medium text-foreground">
                  Tracked branch
                </label>
                <p className="mb-2 text-xs text-foreground-muted">
                  The branch that triggers pipeline runs.
                </p>
                <input
                  id="branch"
                  type="text"
                  value={draft.branch}
                  onChange={(e) => updateDraft("branch", e.target.value)}
                  className="mt-1 w-full max-w-xs rounded-lg border border-border bg-card px-3 py-2 font-mono text-sm text-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/20"
                />
              </div>

              <div className="rounded-xl border border-border bg-background px-4 py-3.5">
                <label htmlFor="deployment-mode" className="block text-sm font-medium text-foreground">
                  Deployment mode
                </label>
                <p className="mb-2 text-xs text-foreground-muted">
                  Controls how deployments are authorized after checks pass.
                </p>
                <select
                  id="deployment-mode"
                  value={draft.deployment_mode}
                  onChange={(e) =>
                    updateDraft(
                      "deployment_mode",
                      e.target.value as PipelineDeploymentMode,
                    )
                  }
                  className="mt-1 w-full max-w-xs rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/20"
                >
                  <option value="require_approval">Require approval</option>
                  <option value="deploy_after_checks">Deploy after checks</option>
                  <option value="validate_only">Validate only</option>
                </select>
              </div>

              <Toggle
                id="automatic-deployment"
                label="Automatic deployment"
                description="Automatically deploy when all pipeline checks pass."
                checked={draft.automatic_deployment}
                onChange={(v) => updateDraft("automatic_deployment", v)}
              />
            </div>
          </section>

          {/* Quality & Testing */}
          <section>
            <h3 className="mb-3 text-sm font-semibold text-foreground">Quality & Testing</h3>
            <div className="space-y-2">
              <Toggle
                id="run-tests"
                label="Run unit tests"
                description="Execute the project's test suite during pipeline runs."
                checked={draft.run_tests}
                onChange={(v) => updateDraft("run_tests", v)}
              />
            </div>
          </section>

          {/* Security scans */}
          <section>
            <h3 className="mb-3 text-sm font-semibold text-foreground">Security Scans</h3>
            <div className="space-y-2">
              <Toggle
                id="sast-enabled"
                label="SAST (Static Analysis)"
                description="Run Semgrep for static application security testing."
                checked={draft.sast_enabled}
                onChange={(v) => updateDraft("sast_enabled", v)}
              />
              <Toggle
                id="dependency-scan"
                label="Dependency scan"
                description="Scan dependencies for known vulnerabilities using Trivy."
                checked={draft.dependency_scan_enabled}
                onChange={(v) => updateDraft("dependency_scan_enabled", v)}
              />
              <Toggle
                id="secret-scan"
                label="Secret scan"
                description="Detect leaked secrets in source code using Gitleaks."
                checked={draft.secret_scan_enabled}
                onChange={(v) => updateDraft("secret_scan_enabled", v)}
              />
              <Toggle
                id="container-scan"
                label="Container scan"
                description="Scan container images for vulnerabilities after build."
                checked={draft.container_scan_enabled}
                onChange={(v) => updateDraft("container_scan_enabled", v)}
              />
              <Toggle
                id="iac-scan"
                label="Infrastructure-as-Code scan"
                description="Validate Terraform and IaC configuration with Checkov and TFLint."
                checked={draft.iac_scan_enabled}
                onChange={(v) => updateDraft("iac_scan_enabled", v)}
              />
            </div>
          </section>

          {/* Deployment controls */}
          <section>
            <h3 className="mb-3 text-sm font-semibold text-foreground">Deployment Controls</h3>
            <div className="space-y-2">
              <Toggle
                id="production-approval"
                label="Require production approval"
                description="Require explicit approval before deploying to production."
                checked={draft.production_approval_required}
                onChange={(v) => updateDraft("production_approval_required", v)}
              />
              <Toggle
                id="auto-rollback"
                label="Auto rollback"
                description="Automatically rollback on deployment failure."
                checked={draft.auto_rollback_enabled}
                onChange={(v) => updateDraft("auto_rollback_enabled", v)}
              />
            </div>
          </section>

          {/* AI & Automation */}
          <section>
            <h3 className="mb-3 text-sm font-semibold text-foreground">AI & Automation</h3>
            <div className="space-y-2">
              <Toggle
                id="ai-diagnosis"
                label="AI failure diagnosis"
                description="Use AI to diagnose pipeline and deployment failures."
                checked={draft.ai_failure_diagnosis_enabled}
                onChange={(v) => updateDraft("ai_failure_diagnosis_enabled", v)}
              />
              <Toggle
                id="auto-retry"
                label="Auto retry transient failures"
                description="Automatically retry stages that fail with transient errors."
                checked={draft.auto_retry_transient_failures}
                onChange={(v) => updateDraft("auto_retry_transient_failures", v)}
              />
            </div>
          </section>

          {/* Save bar */}
          <div className="sticky bottom-0 z-10 -mx-4 border-t border-border bg-card/95 px-4 py-3 backdrop-blur-sm sm:-mx-6 sm:px-6">
            <div className="flex items-center justify-between gap-4">
              <div className="text-xs text-foreground-muted">
                {saveSuccess ? (
                  <span className="inline-flex items-center gap-1 text-success">
                    <Check aria-hidden="true" size={13} />
                    Configuration saved
                  </span>
                ) : saveError ? (
                  <span className="text-danger">{saveError}</span>
                ) : isDirty ? (
                  "Unsaved changes"
                ) : (
                  "No changes"
                )}
              </div>
              <button
                type="button"
                onClick={handleSave}
                disabled={!isDirty || saving}
                className="inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-primary px-4 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? (
                  <Loader2 aria-hidden="true" size={14} className="animate-spin" />
                ) : (
                  <Save aria-hidden="true" size={14} />
                )}
                Save changes
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function toUpdate(config: PipelineConfiguration): PipelineConfigurationUpdate {
  return {
    automatic_deployment: config.automatic_deployment,
    branch: config.branch,
    deployment_mode: config.deployment_mode,
    run_tests: config.run_tests,
    sast_enabled: config.sast_enabled,
    dependency_scan_enabled: config.dependency_scan_enabled,
    secret_scan_enabled: config.secret_scan_enabled,
    container_scan_enabled: config.container_scan_enabled,
    iac_scan_enabled: config.iac_scan_enabled,
    production_approval_required: config.production_approval_required,
    ai_failure_diagnosis_enabled: config.ai_failure_diagnosis_enabled,
    auto_retry_transient_failures: config.auto_retry_transient_failures,
    auto_rollback_enabled: config.auto_rollback_enabled,
  };
}
