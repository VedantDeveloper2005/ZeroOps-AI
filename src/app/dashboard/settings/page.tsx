"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  CheckCircle2,
  Cloud,
  Copy,
  Eye,
  EyeOff,
  GitBranch,
  KeyRound,
  Loader2,
  Save,
  ShieldCheck,
  Trash2,
  UserRound,
  Workflow,
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
  type AzureConnection,
  type EnvVar,
  type GitHubWebhookSecretResponse,
  type PipelineConfiguration,
  type PipelineConfigurationUpdate,
} from "@/lib/api";

type SettingsSection = "workspace" | "pipeline" | "azure" | "variables";
type PipelineSettingsState =
  | "idle"
  | "loading"
  | "ready"
  | "no_record"
  | "unavailable"
  | "error";

type AzureForm = {
  tenant_id: string;
  subscription_id: string;
  client_id: string;
  client_secret: string;
  region: string;
  resource_group: string;
  acr_login_server: string;
  app_service_plan: string;
  aks_cluster_name: string;
  namespace_prefix: string;
};

const emptyAzureForm: AzureForm = {
  tenant_id: "",
  subscription_id: "",
  client_id: "",
  client_secret: "",
  region: "eastus",
  resource_group: "",
  acr_login_server: "",
  app_service_plan: "",
  aks_cluster_name: "",
  namespace_prefix: "",
};

const sections: {
  id: SettingsSection;
  label: string;
  description: string;
  icon: typeof Cloud;
}[] = [
  {
    id: "workspace",
    label: "Workspace",
    description: "Account and project context",
    icon: UserRound,
  },
  {
    id: "pipeline",
    label: "Pipeline",
    description: "Checks and GitHub automation",
    icon: Workflow,
  },
  {
    id: "azure",
    label: "Azure hosting",
    description: "Verified deployment credentials",
    icon: Cloud,
  },
  {
    id: "variables",
    label: "Variables & secrets",
    description: "Production runtime configuration",
    icon: KeyRound,
  },
];

function formatDate(value: string | null) {
  if (!value) return "Date not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date not recorded";
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<SettingsLoading />}>
      <SettingsWorkspace />
    </Suspense>
  );
}

function SettingsWorkspace() {
  const searchParams = useSearchParams();
  const {
    addToast,
    projects,
    isLoading: projectsLoading,
  } = useNotifications();
  const [section, setSection] = useState<SettingsSection>("workspace");
  const [selectedProjectId, setSelectedProjectId] = useState("");

  const [pipelineConfiguration, setPipelineConfiguration] =
    useState<PipelineConfiguration | null>(null);
  const [pipelineState, setPipelineState] =
    useState<PipelineSettingsState>("idle");
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [savingPipeline, setSavingPipeline] = useState(false);
  const [webhookSetup, setWebhookSetup] =
    useState<GitHubWebhookSecretResponse | null>(null);
  const [regeneratingWebhook, setRegeneratingWebhook] = useState(false);

  const [azureConnection, setAzureConnection] = useState<AzureConnection | null>(null);
  const [azureForm, setAzureForm] = useState<AzureForm>(emptyAzureForm);
  const [loadingAzure, setLoadingAzure] = useState(true);
  const [savingAzure, setSavingAzure] = useState(false);
  const [azureError, setAzureError] = useState<string | null>(null);

  const [variables, setVariables] = useState<EnvVar[]>([]);
  const [loadingVariables, setLoadingVariables] = useState(false);
  const [variablesError, setVariablesError] = useState<string | null>(null);
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [isSecret, setIsSecret] = useState(true);
  const [showNewValue, setShowNewValue] = useState(false);
  const [savingVariable, setSavingVariable] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<EnvVar | null>(null);
  const [deletingVariableId, setDeletingVariableId] = useState<string | null>(null);

  useEffect(() => {
    const requestedProject = searchParams.get("project");
    setSelectedProjectId((currentProject) => {
      if (currentProject && projects.some((project) => project.id === currentProject)) {
        return currentProject;
      }
      if (requestedProject && projects.some((project) => project.id === requestedProject)) {
        return requestedProject;
      }
      return projects[0]?.id || "";
    });
  }, [projects, searchParams]);

  useEffect(() => {
    const requestedSection = searchParams.get("tab");
    if (requestedSection === "pipeline") {
      setSection("pipeline");
    } else if (requestedSection === "azure") {
      setSection("azure");
    } else if (requestedSection === "security" || requestedSection === "variables") {
      setSection("variables");
    }
  }, [searchParams]);

  const loadAzureConnection = useCallback(async () => {
    setLoadingAzure(true);
    setAzureError(null);
    try {
      const connection = await api.getAzureConnection();
      setAzureConnection(connection);
      setAzureForm({
        tenant_id: connection.tenant_id || "",
        subscription_id: connection.subscription_id || "",
        client_id: connection.client_id || "",
        client_secret: "",
        region: connection.region || "eastus",
        resource_group: connection.resource_group || "",
        acr_login_server: connection.acr_login_server || "",
        app_service_plan: connection.app_service_plan || "",
        aks_cluster_name: connection.aks_cluster_name || "",
        namespace_prefix: connection.namespace_prefix || "",
      });
    } catch (error) {
      setAzureError(getErrorMessage(error, "Azure connection details could not be loaded."));
    } finally {
      setLoadingAzure(false);
    }
  }, []);

  useEffect(() => {
    void loadAzureConnection();
  }, [loadAzureConnection]);

  const loadPipelineConfiguration = useCallback(async () => {
    if (!selectedProjectId) {
      setPipelineConfiguration(null);
      setPipelineState("idle");
      setPipelineError(null);
      return;
    }

    setPipelineState("loading");
    setPipelineError(null);
    try {
      const configuration = await api.getPipelineConfiguration(selectedProjectId);
      setPipelineConfiguration(configuration);
      setPipelineState("ready");
    } catch (error) {
      setPipelineConfiguration(null);
      if (error instanceof ApiError && error.status === 404) {
        setPipelineState("no_record");
        return;
      }
      if (error instanceof ApiError && error.status === 503) {
        setPipelineState("unavailable");
      } else {
        setPipelineState("error");
      }
      setPipelineError(
        getErrorMessage(error, "Pipeline configuration could not be loaded."),
      );
    }
  }, [selectedProjectId]);

  useEffect(() => {
    setWebhookSetup(null);
    void loadPipelineConfiguration();
  }, [loadPipelineConfiguration]);

  const loadVariables = useCallback(async () => {
    if (!selectedProjectId) {
      setVariables([]);
      return;
    }
    setLoadingVariables(true);
    setVariablesError(null);
    try {
      const data = await api.getEnvVars(selectedProjectId);
      setVariables(data);
    } catch (error) {
      setVariables([]);
      setVariablesError(
        getErrorMessage(error, "Runtime configuration could not be loaded."),
      );
    } finally {
      setLoadingVariables(false);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    setPendingDelete(null);
    setNewKey("");
    setNewValue("");
    void loadVariables();
  }, [loadVariables]);

  const activeProject = projects.find((project) => project.id === selectedProjectId);

  const deploymentFieldsComplete = useMemo(
    () =>
      Boolean(
        azureForm.tenant_id.trim() &&
          azureForm.subscription_id.trim() &&
          azureForm.client_id.trim() &&
          azureForm.resource_group.trim() &&
          azureForm.acr_login_server.trim() &&
          azureForm.app_service_plan.trim(),
      ),
    [azureForm],
  );

  const canSaveAzure =
    deploymentFieldsComplete &&
    Boolean(azureForm.region.trim()) &&
    (azureConnection?.connected || Boolean(azureForm.client_secret.trim()));

  function updateAzureField(field: keyof AzureForm, value: string) {
    setAzureForm((current) => ({ ...current, [field]: value }));
  }

  async function saveAzureConnection(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSaveAzure) return;

    setSavingAzure(true);
    setAzureError(null);
    try {
      const updated = await api.updateAzureConnection({
        tenant_id: azureForm.tenant_id.trim(),
        subscription_id: azureForm.subscription_id.trim(),
        client_id: azureForm.client_id.trim(),
        client_secret: azureForm.client_secret.trim() || undefined,
        region: azureForm.region.trim(),
        resource_group: azureForm.resource_group.trim(),
        acr_login_server: azureForm.acr_login_server.trim().replace(/\/+$/, ""),
        app_service_plan: azureForm.app_service_plan.trim(),
        aks_cluster_name: azureForm.aks_cluster_name.trim() || undefined,
        namespace_prefix: azureForm.namespace_prefix.trim() || undefined,
      });
      setAzureConnection({
        ...azureConnection,
        ...updated,
        connected: true,
        tenant_id: azureForm.tenant_id.trim(),
        subscription_id: azureForm.subscription_id.trim(),
        client_id: azureForm.client_id.trim(),
        region: azureForm.region.trim(),
        resource_group: azureForm.resource_group.trim(),
        acr_login_server: azureForm.acr_login_server.trim().replace(/\/+$/, ""),
        app_service_plan: azureForm.app_service_plan.trim(),
        aks_cluster_name: azureForm.aks_cluster_name.trim() || null,
        namespace_prefix: azureForm.namespace_prefix.trim() || null,
      });
      setAzureForm((current) => ({ ...current, client_secret: "" }));
      addToast("Azure credentials were verified and the deployment target was saved.", "success");
    } catch (error) {
      const message = getErrorMessage(error, "Azure could not verify this deployment target.");
      setAzureError(message);
      addToast(message, "error");
    } finally {
      setSavingAzure(false);
    }
  }

  function updatePipelineField<K extends keyof PipelineConfigurationUpdate>(
    field: K,
    value: PipelineConfigurationUpdate[K],
  ) {
    setPipelineConfiguration((current) =>
      current ? { ...current, [field]: value } : current,
    );
  }

  async function savePipelineConfiguration(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId || !pipelineConfiguration || !pipelineConfiguration.branch.trim()) {
      return;
    }

    const update: PipelineConfigurationUpdate = {
      automatic_deployment: pipelineConfiguration.automatic_deployment,
      branch: pipelineConfiguration.branch.trim(),
      deployment_mode: pipelineConfiguration.deployment_mode,
      run_tests: pipelineConfiguration.run_tests,
      sast_enabled: pipelineConfiguration.sast_enabled,
      dependency_scan_enabled: pipelineConfiguration.dependency_scan_enabled,
      secret_scan_enabled: pipelineConfiguration.secret_scan_enabled,
      container_scan_enabled: pipelineConfiguration.container_scan_enabled,
      iac_scan_enabled: pipelineConfiguration.iac_scan_enabled,
      // Compatibility field: deployment_mode is the authoritative approval policy.
      production_approval_required:
        pipelineConfiguration.deployment_mode === "require_approval",
      ai_failure_diagnosis_enabled: pipelineConfiguration.ai_failure_diagnosis_enabled,
      auto_retry_transient_failures: pipelineConfiguration.auto_retry_transient_failures,
      auto_rollback_enabled: pipelineConfiguration.auto_rollback_enabled,
    };

    setSavingPipeline(true);
    setPipelineError(null);
    try {
      const saved = await api.updatePipelineConfiguration(selectedProjectId, update);
      setPipelineConfiguration(saved);
      setPipelineState("ready");
      addToast("Pipeline configuration was saved.", "success");
    } catch (error) {
      const message = getErrorMessage(error, "Pipeline configuration could not be saved.");
      setPipelineError(message);
      addToast(message, "error");
    } finally {
      setSavingPipeline(false);
    }
  }

  async function regenerateWebhookSecret() {
    if (!selectedProjectId) return;
    if (
      pipelineConfiguration?.github_webhook_secret_configured &&
      !window.confirm(
        "Regenerate the GitHub webhook secret? The existing secret will stop working after you update the webhook in GitHub.",
      )
    ) {
      return;
    }

    setRegeneratingWebhook(true);
    try {
      const setup = await api.regenerateGitHubWebhookSecret(selectedProjectId);
      setWebhookSetup(setup);
      addToast("A webhook secret was generated. Copy it to GitHub now; it will not be shown again.", "success");
      try {
        const refreshed = await api.getPipelineConfiguration(selectedProjectId);
        setPipelineConfiguration(refreshed);
        setPipelineState("ready");
      } catch {
        addToast(
          "The secret was generated, but webhook status could not be refreshed. Keep the displayed values and reload after configuring GitHub.",
          "error",
        );
      }
    } catch (error) {
      addToast(getErrorMessage(error, "The GitHub webhook secret could not be generated."), "error");
    } finally {
      setRegeneratingWebhook(false);
    }
  }

  async function copyWebhookValue(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value);
      addToast(`${label} copied.`, "success");
    } catch {
      addToast("Clipboard access was not available.", "error");
    }
  }

  async function createVariable(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId || !newKey.trim() || !newValue) return;

    setSavingVariable(true);
    try {
      const variable = await api.addEnvVar(selectedProjectId, {
        key: newKey.trim().toUpperCase(),
        value: newValue,
        is_secret: isSecret,
      });
      setVariables((current) => [...current, variable].sort((a, b) => a.key.localeCompare(b.key)));
      setNewKey("");
      setNewValue("");
      setShowNewValue(false);
      addToast(
        isSecret
          ? `${variable.key} was stored in Azure Key Vault.`
          : `${variable.key} was saved as a plain environment value.`,
        "success",
      );
    } catch (error) {
      addToast(getErrorMessage(error, "The environment value could not be saved."), "error");
    } finally {
      setSavingVariable(false);
    }
  }

  async function deleteVariable() {
    if (!selectedProjectId || !pendingDelete) return;

    setDeletingVariableId(pendingDelete.id);
    try {
      await api.deleteEnvVar(selectedProjectId, pendingDelete.id);
      setVariables((current) => current.filter((variable) => variable.id !== pendingDelete.id));
      addToast(`${pendingDelete.key} was deleted.`, "success");
      setPendingDelete(null);
    } catch (error) {
      addToast(getErrorMessage(error, "The environment value could not be deleted."), "error");
    } finally {
      setDeletingVariableId(null);
    }
  }

  return (
    <div className="pb-8">
      <PageHeader
        eyebrow="Configuration"
        title="Settings"
        description="Manage project pipeline policy, verified Azure targets, and production runtime values."
        actions={
          !projectsLoading && projects.length > 0 ? (
            <ProjectSelector
              projects={projects}
              value={selectedProjectId}
              onChange={setSelectedProjectId}
              className="w-full sm:w-72"
            />
          ) : undefined
        }
      />

      {activeProject && (
        <section aria-label="Selected project settings" className="mb-6 rounded-xl border border-border bg-card px-3 pt-3 shadow-sm sm:px-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2 px-1">
            <p className="text-xs font-medium text-foreground-muted">
              Configuring <span className="font-semibold text-foreground">{activeProject.name}</span>
            </p>
            <p className="font-mono text-xs text-foreground-subtle">
              {activeProject.branch || "Default branch"}
            </p>
          </div>
          <ProjectTabs projectId={activeProject.id} />
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <nav aria-label="Settings sections" className="rounded-xl border border-border bg-card p-2 shadow-sm lg:sticky lg:top-24 lg:self-start">
          <p className="hidden px-3 pb-2 pt-1 text-xs font-semibold text-foreground-muted lg:block">
            Settings areas
          </p>
          <div className="flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible">
            {sections.map((item) => {
              const Icon = item.icon;
              const selected = item.id === section;
              return (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setSection(item.id)}
                  className={`flex min-h-12 min-w-max items-center gap-3 rounded-lg border px-3 text-left transition-colors lg:w-full ${
                    selected
                      ? "border-primary/25 bg-primary-subtle text-primary"
                      : "border-transparent text-foreground-muted hover:border-border hover:bg-card hover:text-foreground"
                  }`}
                >
                  <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg ${selected ? "bg-card text-primary shadow-sm" : "bg-surface-subtle text-foreground-muted"}`}>
                    <Icon size={16} aria-hidden="true" />
                  </span>
                  <span>
                    <span className="block text-xs font-semibold">{item.label}</span>
                    <span className="mt-0.5 hidden text-xs leading-5 text-foreground-subtle lg:block">
                      {item.description}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </nav>

        <div className="min-w-0">
          {section === "workspace" && (
            <WorkspaceSettings
              activeProject={activeProject}
              projectsLoading={projectsLoading}
            />
          )}

          {section === "azure" && (
            <AzureSettings
              connection={azureConnection}
              form={azureForm}
              loading={loadingAzure}
              saving={savingAzure}
              error={azureError}
              deploymentFieldsComplete={deploymentFieldsComplete}
              canSave={canSaveAzure}
              onChange={updateAzureField}
              onSave={saveAzureConnection}
              onRetry={() => void loadAzureConnection()}
            />
          )}

          {section === "pipeline" && (
            <PipelineSettings
              hasProjects={projects.length > 0}
              loadingProjects={projectsLoading}
              projectName={activeProject?.name}
              configuration={pipelineConfiguration}
              state={pipelineState}
              error={pipelineError}
              saving={savingPipeline}
              webhookSetup={webhookSetup}
              regeneratingWebhook={regeneratingWebhook}
              onChange={updatePipelineField}
              onSave={savePipelineConfiguration}
              onRegenerateWebhook={() => void regenerateWebhookSecret()}
              onCopyWebhookValue={(value, label) => void copyWebhookValue(value, label)}
              onClearWebhookSetup={() => setWebhookSetup(null)}
              onRetry={() => void loadPipelineConfiguration()}
            />
          )}

          {section === "variables" && (
            <VariablesSettings
              activeProjectName={activeProject?.name}
              hasProjects={projects.length > 0}
              loadingProjects={projectsLoading}
              variables={variables}
              loading={loadingVariables}
              error={variablesError}
              newKey={newKey}
              newValue={newValue}
              isSecret={isSecret}
              showNewValue={showNewValue}
              saving={savingVariable}
              pendingDelete={pendingDelete}
              deletingVariableId={deletingVariableId}
              onKeyChange={setNewKey}
              onValueChange={setNewValue}
              onSecretChange={setIsSecret}
              onToggleValue={() => setShowNewValue((visible) => !visible)}
              onCreate={createVariable}
              onRequestDelete={setPendingDelete}
              onCancelDelete={() => setPendingDelete(null)}
              onConfirmDelete={() => void deleteVariable()}
              onRetry={() => void loadVariables()}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function WorkspaceSettings({
  activeProject,
  projectsLoading,
}: {
  activeProject: ReturnType<typeof useNotifications>["projects"][number] | undefined;
  projectsLoading: boolean;
}) {
  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6">
        <div className="mb-5">
          <h2 className="text-base font-semibold text-foreground">Account preferences</h2>
          <p className="mt-1 text-xs leading-5 text-foreground-muted">
            Identity, multi-factor authentication, and notification records have dedicated settings.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Link
            href="/dashboard/profile"
            className="group flex min-h-24 items-center gap-4 rounded-lg border border-border p-4 transition-colors hover:bg-surface-raised"
          >
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-primary-subtle text-primary">
              <UserRound size={18} aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold text-foreground">Profile & security</span>
              <span className="mt-1 block text-xs leading-5 text-foreground-muted">
                Update your profile and manage MFA.
              </span>
            </span>
            <ArrowRight size={16} className="text-foreground-subtle group-hover:text-primary" aria-hidden="true" />
          </Link>
          <Link
            href="/dashboard/incidents"
            className="group flex min-h-24 items-center gap-4 rounded-lg border border-border p-4 transition-colors hover:bg-surface-raised"
          >
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-info-subtle text-info">
              <Bell size={18} aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold text-foreground">Notification inbox</span>
              <span className="mt-1 block text-xs leading-5 text-foreground-muted">
                Review persisted account and deployment notices.
              </span>
            </span>
            <ArrowRight size={16} className="text-foreground-subtle group-hover:text-primary" aria-hidden="true" />
          </Link>
        </div>
      </section>

      {projectsLoading ? (
        <SettingsLoading />
      ) : !activeProject ? (
        <StatePanel
          title="No project selected"
          description="Connect a repository or upload a ZIP archive before configuring project runtime values."
          action={{ label: "Connect code", href: "/dashboard/repositories" }}
        />
      ) : (
        <section className="rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-primary">
                Selected project
              </p>
              <h2 className="mt-2 text-base font-semibold text-foreground">{activeProject.name}</h2>
              <p className="mt-1 text-xs text-foreground-muted">
                {activeProject.full_name.startsWith("upload/")
                  ? "Uploaded source archive"
                  : activeProject.full_name}
              </p>
            </div>
            <Link href={`/dashboard/apps/${activeProject.id}`} className="ops-secondary">
              Open project <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </div>
          <dl className="mt-5 grid gap-4 border-t border-border pt-5 text-xs sm:grid-cols-3">
            <div>
              <dt className="text-foreground-subtle">Framework</dt>
              <dd className="mt-1 font-medium text-foreground">{activeProject.framework || "Not detected"}</dd>
            </div>
            <div>
              <dt className="text-foreground-subtle">Configured branch</dt>
              <dd className="mt-1 font-mono text-xs font-medium text-foreground">
                {activeProject.branch || "Not recorded"}
              </dd>
            </div>
            <div>
              <dt className="text-foreground-subtle">Deployment region</dt>
              <dd className="mt-1 font-medium text-foreground">{activeProject.region || "Not selected"}</dd>
            </div>
          </dl>
        </section>
      )}
    </div>
  );
}

function PipelineSettings({
  hasProjects,
  loadingProjects,
  projectName,
  configuration,
  state,
  error,
  saving,
  webhookSetup,
  regeneratingWebhook,
  onChange,
  onSave,
  onRegenerateWebhook,
  onCopyWebhookValue,
  onClearWebhookSetup,
  onRetry,
}: {
  hasProjects: boolean;
  loadingProjects: boolean;
  projectName?: string;
  configuration: PipelineConfiguration | null;
  state: PipelineSettingsState;
  error: string | null;
  saving: boolean;
  webhookSetup: GitHubWebhookSecretResponse | null;
  regeneratingWebhook: boolean;
  onChange: <K extends keyof PipelineConfigurationUpdate>(
    field: K,
    value: PipelineConfigurationUpdate[K],
  ) => void;
  onSave: (event: React.FormEvent<HTMLFormElement>) => void;
  onRegenerateWebhook: () => void;
  onCopyWebhookValue: (value: string, label: string) => void;
  onClearWebhookSetup: () => void;
  onRetry: () => void;
}) {
  if (loadingProjects || state === "loading") {
    return <SettingsLoading label="Loading pipeline configuration…" />;
  }

  if (!hasProjects) {
    return (
      <StatePanel
        title="No project pipeline to configure"
        description="Connect a repository before configuring validation and deployment behavior."
        action={{ label: "Connect a project", href: "/dashboard/repositories" }}
      />
    );
  }

  if (state === "no_record") {
    return (
      <StatePanel
        title="No pipeline configuration is stored"
        description="The backend returned no configuration for this project, so ZeroOps is not displaying assumed defaults."
        action={{ label: "Check again", onClick: onRetry }}
      />
    );
  }

  if (state === "unavailable") {
    return (
      <StatePanel
        variant="disconnected"
        title="Pipeline configuration service unavailable"
        description={error || "The backend cannot currently provide project pipeline policy. Existing behavior has not been inferred."}
        action={{ label: "Try again", onClick: onRetry }}
      />
    );
  }

  if (!configuration) {
    return (
      <StatePanel
        variant="error"
        title="Pipeline configuration could not be loaded"
        description={error || "No configuration response was returned."}
        action={{ label: "Try again", onClick: onRetry }}
      />
    );
  }

  return (
    <form onSubmit={onSave} className="space-y-5">
      <section className="rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6">
        <div className="flex flex-col gap-3 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Workflow size={17} className="text-primary" aria-hidden="true" />
              <h2 className="text-base font-semibold text-foreground">Pipeline policy</h2>
            </div>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-foreground-muted">
              Stored execution settings for {projectName || "the selected project"}. Irrelevant stages may still be skipped by change and target detection.
            </p>
          </div>
          <span className="rounded-full border border-border bg-surface-subtle px-3 py-1.5 text-xs font-semibold text-foreground-muted">
            {configuration.github_webhook_secret_configured
              ? "Signing secret stored"
              : "No signing secret stored"}
          </span>
        </div>

        {error && (
          <p role="alert" className="mt-4 rounded-lg border border-danger/25 bg-danger-subtle px-3 py-2 text-xs text-danger">
            {error}
          </p>
        )}

        <fieldset className="mt-5">
          <legend className="text-sm font-semibold text-foreground">GitHub automation</legend>
          <p className="mt-1 text-xs leading-5 text-foreground-muted">
            This screen reports only whether a signing secret is stored. Install the webhook in GitHub separately; installation and event delivery are not verified here.
          </p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label htmlFor="pipeline-branch">
              <span className="mb-1.5 flex items-center gap-2 text-xs font-medium text-foreground-muted">
                <GitBranch size={14} aria-hidden="true" /> Branch
              </span>
              <input
                id="pipeline-branch"
                value={configuration.branch}
                onChange={(event) => onChange("branch", event.target.value)}
                required
                autoComplete="off"
                className="ops-input"
              />
            </label>
            <label htmlFor="pipeline-mode">
              <span className="mb-1.5 block text-xs font-medium text-foreground-muted">
                Push behavior
              </span>
              <select
                id="pipeline-mode"
                value={configuration.deployment_mode}
                onChange={(event) =>
                  onChange(
                    "deployment_mode",
                    event.target.value as PipelineConfiguration["deployment_mode"],
                  )
                }
                className="ops-input"
              >
                <option value="validate_only">Validate only; deploy manually</option>
                <option value="deploy_after_checks">Deploy after required checks</option>
                <option value="require_approval">Require approval before deploy</option>
              </select>
            </label>
          </div>
          <div className="mt-4">
            <PipelineToggle
              id="pipeline-auto-deploy"
              label="Automatic deployment on push"
              description={
                configuration.github_webhook_secret_configured
                  ? "Allow authenticated push events for the configured branch. A stored secret does not prove the repository webhook is installed or delivering events."
                  : "Generate a signing secret and install the returned URL and secret in GitHub before enabling push events."
              }
              checked={configuration.automatic_deployment}
              disabled={!configuration.github_webhook_secret_configured}
              onChange={(checked) => onChange("automatic_deployment", checked)}
            />
          </div>

          <div className="mt-4 rounded-lg border border-border bg-surface-subtle p-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-semibold text-foreground">GitHub webhook credential</p>
                <p className="mt-1 text-xs leading-5 text-foreground-muted">
                  Generate a project-specific signing secret, then add the returned URL and secret to the repository webhook settings in GitHub.
                </p>
              </div>
              <button
                type="button"
                onClick={onRegenerateWebhook}
                disabled={regeneratingWebhook}
                className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground hover:bg-surface-raised disabled:opacity-50"
              >
                {regeneratingWebhook ? <Loader2 size={14} className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <KeyRound size={14} aria-hidden="true" />}
                {regeneratingWebhook
                  ? "Generating…"
                  : configuration.github_webhook_secret_configured
                    ? "Regenerate secret"
                    : "Generate secret"}
              </button>
            </div>

            {webhookSetup && (
              <div role="status" className="mt-3 space-y-3 rounded-lg border border-warning/25 bg-warning-subtle p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs font-semibold text-warning">Shown once — copy these values now</p>
                  <button
                    type="button"
                    onClick={onClearWebhookSetup}
                    className="min-h-11 rounded-md px-2 text-xs font-semibold text-foreground-muted hover:bg-card hover:text-foreground"
                  >
                    Hide secret
                  </button>
                </div>
                <p className="text-xs leading-5 text-foreground-muted">{webhookSetup.warning}</p>
                {[
                  ["Payload URL", webhookSetup.webhook_url],
                  ["Webhook secret", webhookSetup.secret],
                ].map(([label, value]) => (
                  <div key={label}>
                    <p className="text-xs font-semibold text-foreground-subtle">{label}</p>
                    <div className="mt-1 flex gap-2">
                      <code className="min-w-0 flex-1 overflow-x-auto rounded-md border border-border bg-card px-2.5 py-2 text-xs text-foreground">{value}</code>
                      <button
                        type="button"
                        onClick={() => onCopyWebhookValue(value, label)}
                        aria-label={`Copy ${label.toLowerCase()}`}
                        className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg border border-border bg-card text-foreground hover:bg-surface-raised"
                      >
                        <Copy size={14} aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </fieldset>
      </section>

      <section className="rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6">
        <fieldset>
          <legend className="text-sm font-semibold text-foreground">Deterministic checks</legend>
          <p className="mt-1 text-xs leading-5 text-foreground-muted">
            Enabling a check requests the corresponding recorded stage. A missing required scanner must be reported as unavailable or blocked, never passed.
          </p>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <PipelineToggle id="pipeline-tests" label="Unit tests" description="Run the detected project test command." checked={configuration.run_tests} onChange={(checked) => onChange("run_tests", checked)} />
            <PipelineToggle id="pipeline-sast" label="SAST" description="Run the configured source-code scanner." checked={configuration.sast_enabled} onChange={(checked) => onChange("sast_enabled", checked)} />
            <PipelineToggle id="pipeline-dependencies" label="Dependency scan" description="Inspect supported package dependencies." checked={configuration.dependency_scan_enabled} onChange={(checked) => onChange("dependency_scan_enabled", checked)} />
            <PipelineToggle id="pipeline-secrets" label="Secret scan" description="Scan for exposed credential patterns; values remain redacted." checked={configuration.secret_scan_enabled} onChange={(checked) => onChange("secret_scan_enabled", checked)} />
            <PipelineToggle id="pipeline-container" label="Container scan" description="Runs only when the selected target produces a container." checked={configuration.container_scan_enabled} onChange={(checked) => onChange("container_scan_enabled", checked)} />
            <PipelineToggle id="pipeline-iac" label="IaC scan" description="Runs only when infrastructure files are relevant." checked={configuration.iac_scan_enabled} onChange={(checked) => onChange("iac_scan_enabled", checked)} />
          </div>
        </fieldset>
      </section>

      <section className="rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6">
        <fieldset>
          <legend className="text-sm font-semibold text-foreground">Failure and approval policy</legend>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border border-border bg-surface-subtle p-3">
              <p className="text-xs font-semibold text-foreground">Approval gate</p>
              <p className="mt-1 text-xs leading-5 text-foreground-muted">
                {configuration.deployment_mode === "require_approval"
                  ? "Required by the selected push behavior. A validated release stops for an authenticated approval."
                  : "Not required by the selected push behavior. Change the deployment mode above to require approval."}
              </p>
              <p className="mt-2 text-xs font-semibold text-foreground-subtle">
                Derived from deployment mode
              </p>
            </div>
            <PipelineToggle id="pipeline-ai-diagnosis" label="AI failure diagnosis" description="Allow sanitized failure context to be investigated after a failed stage." checked={configuration.ai_failure_diagnosis_enabled} onChange={(checked) => onChange("ai_failure_diagnosis_enabled", checked)} />
            <PipelineToggle id="pipeline-auto-retry" label="Retry transient failures" description="Allow only policy-classified transient operations to be retried." checked={configuration.auto_retry_transient_failures} onChange={(checked) => onChange("auto_retry_transient_failures", checked)} />
            <PipelineToggle id="pipeline-auto-rollback" label="Automatic rollback" description="Permit rollback only where backend policy marks it safe and authorized." checked={configuration.auto_rollback_enabled} onChange={(checked) => onChange("auto_rollback_enabled", checked)} />
          </div>
        </fieldset>

        <div className="mt-5 flex flex-col gap-3 border-t border-border pt-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-foreground-muted">
            Last saved: {configuration.updated_at ? formatDate(configuration.updated_at) : "not recorded"}
          </p>
          <button
            type="submit"
            disabled={saving || !configuration.branch.trim()}
            className="ops-primary sm:shrink-0"
          >
            {saving ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <Save size={15} aria-hidden="true" />}
            {saving ? "Saving…" : "Save pipeline policy"}
          </button>
        </div>
      </section>
    </form>
  );
}

function PipelineToggle({
  id,
  label,
  description,
  checked,
  disabled = false,
  onChange,
}: {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label
      htmlFor={id}
      className="flex min-h-20 cursor-pointer items-start gap-3 rounded-lg border border-border bg-surface-subtle px-3 py-3 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-primary/30 has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60"
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-0.5 h-5 w-5 shrink-0 accent-primary"
      />
      <span>
        <span className="block text-xs font-semibold text-foreground">{label}</span>
        <span className="mt-1 block text-xs leading-5 text-foreground-muted">{description}</span>
      </span>
    </label>
  );
}

function AzureSettings({
  connection,
  form,
  loading,
  saving,
  error,
  deploymentFieldsComplete,
  canSave,
  onChange,
  onSave,
  onRetry,
}: {
  connection: AzureConnection | null;
  form: AzureForm;
  loading: boolean;
  saving: boolean;
  error: string | null;
  deploymentFieldsComplete: boolean;
  canSave: boolean;
  onChange: (field: keyof AzureForm, value: string) => void;
  onSave: (event: React.FormEvent<HTMLFormElement>) => void;
  onRetry: () => void;
}) {
  if (loading) return <SettingsLoading label="Loading Azure deployment target…" />;

  return (
    <div className="space-y-5">
      {error && (
        <StatePanel
          variant="error"
          title="Azure settings need attention"
          description={error}
          action={{ label: "Reload saved settings", onClick: onRetry }}
          compact
        />
      )}

      <section className="rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6">
        <div className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">Azure deployment targets</h2>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-foreground-muted">
              App Service remains the active managed-web target. You may record an existing AKS cluster for Kubernetes readiness checks, but AKS release mutation is currently blocked.
            </p>
          </div>
          <span
            className={`inline-flex w-fit items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${
              connection?.connected
                ? "border-success/25 bg-success-subtle text-success"
                : "border-warning/25 bg-warning-subtle text-warning"
            }`}
          >
            {connection?.connected ? (
              <CheckCircle2 size={13} aria-hidden="true" />
            ) : (
              <AlertTriangle size={13} aria-hidden="true" />
            )}
            {connection?.connected ? "Verified connection" : "Not connected"}
          </span>
        </div>

        <div className="my-5 rounded-lg border border-info/20 bg-info-subtle p-4 text-xs leading-5 text-foreground-muted">
          <div className="flex gap-3">
            <ShieldCheck size={18} className="mt-0.5 shrink-0 text-info" aria-hidden="true" />
            <p>
              The client secret is written to Azure Key Vault and is never returned to this page.
              Saving fails if Key Vault is unavailable. Use a service principal scoped to the
              configured resource group.
            </p>
          </div>
        </div>

        <form onSubmit={onSave} className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <SettingsField
              id="azure-tenant"
              label="Tenant ID"
              value={form.tenant_id}
              onChange={(value) => onChange("tenant_id", value)}
              autoComplete="off"
              required
            />
            <SettingsField
              id="azure-subscription"
              label="Subscription ID"
              value={form.subscription_id}
              onChange={(value) => onChange("subscription_id", value)}
              autoComplete="off"
              required
            />
            <SettingsField
              id="azure-client"
              label="Client ID"
              value={form.client_id}
              onChange={(value) => onChange("client_id", value)}
              autoComplete="off"
              required
            />
            <SettingsField
              id="azure-secret"
              label={connection?.connected ? "Client secret (leave blank to keep current)" : "Client secret"}
              value={form.client_secret}
              onChange={(value) => onChange("client_secret", value)}
              type="password"
              autoComplete="new-password"
              required={!connection?.connected}
            />
            <SettingsField
              id="azure-resource-group"
              label="Resource group"
              value={form.resource_group}
              onChange={(value) => onChange("resource_group", value)}
              autoComplete="off"
              required
            />
            <SettingsField
              id="azure-region"
              label="Azure region"
              value={form.region}
              onChange={(value) => onChange("region", value)}
              autoComplete="off"
              required
            />
            <SettingsField
              id="azure-registry"
              label="Container registry login server"
              value={form.acr_login_server}
              onChange={(value) => onChange("acr_login_server", value)}
              placeholder="example.azurecr.io"
              autoComplete="off"
              required
            />
            <SettingsField
              id="azure-plan"
              label="Linux App Service plan"
              value={form.app_service_plan}
              onChange={(value) => onChange("app_service_plan", value)}
              autoComplete="off"
              required
            />
            <SettingsField
              id="azure-aks-cluster"
              label="Existing AKS cluster (optional)"
              value={form.aks_cluster_name}
              onChange={(value) => onChange("aks_cluster_name", value)}
              autoComplete="off"
            />
            <SettingsField
              id="azure-prefix"
              label="Application name prefix (optional)"
              value={form.namespace_prefix}
              onChange={(value) => onChange("namespace_prefix", value)}
              autoComplete="off"
            />
          </div>

          <p className="rounded-lg border border-warning/25 bg-warning-subtle px-3 py-2.5 text-xs leading-5 text-foreground-muted">
            Saving an AKS cluster name records an existing target only. This form does not create a cluster or prove workload readiness. AKS deployment remains unavailable until hardened Service/Ingress verification is implemented.
          </p>

          <div className="flex flex-col gap-3 border-t border-border pt-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs leading-5 text-foreground-muted">
              {deploymentFieldsComplete
                ? "All App Service deployment fields are present."
                : "Complete every required field before this target can be used for deployment."}
            </p>
            <button type="submit" disabled={!canSave || saving} className="ops-primary sm:shrink-0">
              {saving ? (
                <Loader2 size={15} className="animate-spin" aria-hidden="true" />
              ) : (
                <Save size={15} aria-hidden="true" />
              )}
              {saving
                ? "Verifying…"
                : connection?.connected
                  ? "Verify & save"
                  : "Connect Azure"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function SettingsField({
  id,
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  autoComplete,
  required,
  className,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  placeholder?: string;
  autoComplete?: string;
  required?: boolean;
  className?: string;
}) {
  return (
    <label htmlFor={id} className={className}>
      <span className="mb-1.5 block text-xs font-medium text-foreground-muted">
        {label}
        {required && <span className="ml-1 text-danger" aria-hidden="true">*</span>}
      </span>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        required={required}
        className="min-h-11 w-full rounded-lg border border-border bg-surface-subtle px-3 text-sm text-foreground outline-none placeholder:text-foreground-subtle focus:border-primary focus:ring-2 focus:ring-primary/15"
      />
    </label>
  );
}

function VariablesSettings({
  activeProjectName,
  hasProjects,
  loadingProjects,
  variables,
  loading,
  error,
  newKey,
  newValue,
  isSecret,
  showNewValue,
  saving,
  pendingDelete,
  deletingVariableId,
  onKeyChange,
  onValueChange,
  onSecretChange,
  onToggleValue,
  onCreate,
  onRequestDelete,
  onCancelDelete,
  onConfirmDelete,
  onRetry,
}: {
  activeProjectName?: string;
  hasProjects: boolean;
  loadingProjects: boolean;
  variables: EnvVar[];
  loading: boolean;
  error: string | null;
  newKey: string;
  newValue: string;
  isSecret: boolean;
  showNewValue: boolean;
  saving: boolean;
  pendingDelete: EnvVar | null;
  deletingVariableId: string | null;
  onKeyChange: (value: string) => void;
  onValueChange: (value: string) => void;
  onSecretChange: (value: boolean) => void;
  onToggleValue: () => void;
  onCreate: (event: React.FormEvent<HTMLFormElement>) => void;
  onRequestDelete: (variable: EnvVar) => void;
  onCancelDelete: () => void;
  onConfirmDelete: () => void;
  onRetry: () => void;
}) {
  if (loadingProjects) return <SettingsLoading />;
  if (!hasProjects || !activeProjectName) {
    return (
      <StatePanel
        title="No project available"
        description="Connect a repository or upload a ZIP archive before adding runtime configuration."
        action={{ label: "Connect code", href: "/dashboard/repositories" }}
      />
    );
  }

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6">
        <div className="mb-5">
          <h2 className="text-base font-semibold text-foreground">Add runtime configuration</h2>
          <p className="mt-1 text-xs leading-5 text-foreground-muted">
            Values in this section apply to the production environment for{" "}
            <span className="font-medium text-foreground">{activeProjectName}</span>.
          </p>
        </div>

        <div className="mb-5 rounded-lg border border-info/20 bg-info-subtle p-4">
          <div className="flex gap-3">
            <ShieldCheck size={18} className="mt-0.5 shrink-0 text-info" aria-hidden="true" />
            <p className="text-xs leading-5 text-foreground-muted">
              Secrets are stored only in Azure Key Vault and are always returned masked.
              Non-secret values are stored in the application database and returned to authorized
              project owners, so use that option only for non-sensitive configuration.
            </p>
          </div>
        </div>

        <form onSubmit={onCreate} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
            <label htmlFor="variable-key">
              <span className="mb-1.5 block text-xs font-medium text-foreground-muted">Name</span>
              <input
                id="variable-key"
                value={newKey}
                onChange={(event) =>
                  onKeyChange(event.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ""))
                }
                placeholder="DATABASE_URL"
                pattern="[A-Z][A-Z0-9_]*"
                maxLength={255}
                autoComplete="off"
                required
                className="min-h-11 w-full rounded-lg border border-border bg-surface-subtle px-3 font-mono text-sm text-foreground outline-none placeholder:text-foreground-subtle focus:border-primary focus:ring-2 focus:ring-primary/15"
              />
            </label>
            <label htmlFor="variable-value">
              <span className="mb-1.5 block text-xs font-medium text-foreground-muted">Value</span>
              <span className="relative block">
                <input
                  id="variable-value"
                  type={isSecret && !showNewValue ? "password" : "text"}
                  value={newValue}
                  onChange={(event) => onValueChange(event.target.value)}
                  autoComplete={isSecret ? "new-password" : "off"}
                  maxLength={65536}
                  required
                  className="min-h-11 w-full rounded-lg border border-border bg-surface-subtle px-3 pr-11 font-mono text-sm text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
                />
                {isSecret && (
                  <button
                    type="button"
                    onClick={onToggleValue}
                    aria-label={showNewValue ? "Hide secret value" : "Show secret value"}
                    className="absolute right-1 top-1 grid h-9 w-9 place-items-center rounded-md text-foreground-muted hover:bg-surface-raised hover:text-foreground"
                  >
                    {showNewValue ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                )}
              </span>
            </label>
          </div>

          <div className="flex flex-col gap-4 rounded-lg border border-border bg-surface-subtle p-3 sm:flex-row sm:items-center sm:justify-between">
            <label className="flex min-h-11 cursor-pointer items-center gap-3">
              <input
                type="checkbox"
                checked={isSecret}
                onChange={(event) => onSecretChange(event.target.checked)}
                className="h-4 w-4 rounded border-border accent-primary"
              />
              <span>
                <span className="block text-xs font-semibold text-foreground">Sensitive value</span>
                <span className="mt-0.5 block text-xs text-foreground-muted">
                  {isSecret ? "Store in Azure Key Vault" : "Store as plain database value"}
                </span>
              </span>
            </label>
            <button
              type="submit"
              disabled={saving || !newKey.trim() || !newValue}
              className="ops-primary sm:shrink-0"
            >
              {saving ? (
                <Loader2 size={15} className="animate-spin" aria-hidden="true" />
              ) : (
                <KeyRound size={15} aria-hidden="true" />
              )}
              {saving ? "Saving…" : "Save value"}
            </button>
          </div>
        </form>
      </section>

      <section className="rounded-xl border border-border bg-card shadow-sm">
        <div className="flex flex-col gap-1 border-b border-border p-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div>
            <h2 className="text-base font-semibold text-foreground">Saved values</h2>
            <p className="mt-1 text-xs text-foreground-muted">
              {variables.length} {variables.length === 1 ? "value" : "values"} recorded
            </p>
          </div>
        </div>

        {error ? (
          <div className="p-5 sm:p-6">
            <StatePanel
              variant="error"
              title="Runtime configuration is unavailable"
              description={error}
              action={{ label: "Retry", onClick: onRetry }}
              compact
            />
          </div>
        ) : loading ? (
          <SettingsLoading label="Loading runtime configuration…" />
        ) : variables.length === 0 ? (
          <div className="p-5 sm:p-6">
            <StatePanel
              title="No runtime values configured"
              description="Add only the values your application needs. ZeroOps does not create sample secrets."
              compact
            />
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {variables.map((variable) => (
              <li key={variable.id} className="p-4 sm:px-6">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <span
                    className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${
                      variable.is_secret
                        ? "bg-warning-subtle text-warning"
                        : "bg-surface-subtle text-foreground-muted"
                    }`}
                  >
                    {variable.is_secret ? (
                      <ShieldCheck size={16} aria-hidden="true" />
                    ) : (
                      <KeyRound size={16} aria-hidden="true" />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <code className="break-all text-xs font-semibold text-foreground">{variable.key}</code>
                      <span className="rounded-full border border-border bg-surface-subtle px-2.5 py-1 text-xs font-medium text-foreground-muted">
                        {variable.is_secret ? "Key Vault secret" : "Plain value"}
                      </span>
                    </div>
                    <p className="mt-1 truncate font-mono text-xs text-foreground-subtle">
                      {variable.is_secret ? "Value is masked and cannot be retrieved" : variable.value}
                    </p>
                    <p className="mt-1 text-xs text-foreground-subtle">
                      Added {formatDate(variable.created_at)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => onRequestDelete(variable)}
                    disabled={Boolean(deletingVariableId)}
                    aria-label={`Delete ${variable.key}`}
                    className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-border px-3 text-xs font-medium text-danger transition-colors hover:border-danger/30 hover:bg-danger-subtle disabled:cursor-not-allowed disabled:opacity-50 sm:shrink-0"
                  >
                    <Trash2 size={14} aria-hidden="true" />
                    Delete
                  </button>
                </div>

                {pendingDelete?.id === variable.id && (
                  <div
                    role="alert"
                    className="mt-4 rounded-lg border border-danger/25 bg-danger-subtle p-4"
                  >
                    <div className="flex gap-3">
                      <AlertTriangle size={18} className="mt-0.5 shrink-0 text-danger" aria-hidden="true" />
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-semibold text-foreground">
                          Delete {variable.key}?
                        </p>
                        <p className="mt-1 text-xs leading-5 text-foreground-muted">
                          This removes the database record
                          {variable.is_secret ? " and starts deletion of the Key Vault secret" : ""}.
                          A running application may fail if it still depends on this value.
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={onCancelDelete}
                            disabled={deletingVariableId === variable.id}
                            className="ops-secondary"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={onConfirmDelete}
                            disabled={deletingVariableId === variable.id}
                            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-danger px-3 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {deletingVariableId === variable.id ? (
                              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                            ) : (
                              <Trash2 size={14} aria-hidden="true" />
                            )}
                            {deletingVariableId === variable.id ? "Deleting…" : "Delete value"}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function SettingsLoading({ label = "Loading settings…" }: { label?: string }) {
  return (
    <div
      aria-busy="true"
      className="flex min-h-40 items-center justify-center gap-2 rounded-xl border border-border bg-card text-sm text-foreground-muted"
    >
      <Loader2 size={18} className="animate-spin text-primary" aria-hidden="true" />
      {label}
    </div>
  );
}
