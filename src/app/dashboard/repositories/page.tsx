"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  FileArchive,
  GitBranch,
  Loader2,
  Search,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { useAuth } from "@/lib/AuthContext";
import { useNotifications } from "@/lib/NotificationContext";
import {
  api,
  getErrorMessage,
  type GitHubRepoItem,
  type InfrastructurePlan,
} from "@/lib/api";

type AppReview = {
  framework: string | null;
  applicationType: string | null;
  explanation: string | null;
  environmentVariables: string[];
};

const asString = (value: unknown) =>
  typeof value === "string" && value.trim() ? value.trim() : null;

const asStrings = (value: unknown) =>
  Array.isArray(value)
    ? value.filter(
        (item): item is string => typeof item === "string" && item.trim().length > 0,
      )
    : [];

const toReview = (data: Record<string, unknown>): AppReview => ({
  framework: asString(data.framework),
  applicationType: asString(data.application_type),
  explanation: asString(data.explanation),
  environmentVariables: asStrings(data.environment_variables),
});

const sourceDate = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Update date unavailable";
  return `Updated ${date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  })}`;
};

export default function RepositoriesPage() {
  const router = useRouter();
  const { user, loginWithGitHub } = useAuth();
  const { addToast, refreshProjects, refreshStats, projects } = useNotifications();
  const latestRepoRequest = useRef(0);
  const [repos, setRepos] = useState<GitHubRepoItem[]>([]);
  const [repoSearch, setRepoSearch] = useState("");
  const [selectedRepo, setSelectedRepo] = useState<GitHubRepoItem | null>(null);
  const [branch, setBranch] = useState("main");
  const [branches, setBranches] = useState<string[]>(["main"]);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [loadingBranches, setLoadingBranches] = useState(false);
  const [branchError, setBranchError] = useState<string | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [infrastructurePlan, setInfrastructurePlan] = useState<InfrastructurePlan | null>(null);
  const [sourceName, setSourceName] = useState<string | null>(null);
  const [review, setReview] = useState<AppReview | null>(null);
  const [isReviewing, setIsReviewing] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const githubConnected = user?.github_connected === true;
  const currentStep = review ? 3 : selectedRepo || uploadFile ? 2 : 1;

  const loadRepos = useCallback(
    async (query = "") => {
      if (!githubConnected) return;
      const requestId = latestRepoRequest.current + 1;
      latestRepoRequest.current = requestId;
      setLoadingRepos(true);
      setError(null);
      try {
        const result = await api.getGitHubRepos({
          page: 1,
          per_page: 50,
          sort: "updated",
          q: query || undefined,
        });
        if (latestRepoRequest.current === requestId) {
          setRepos(result.repos);
        }
      } catch (repoError) {
        if (latestRepoRequest.current === requestId) {
          setError(
            getErrorMessage(repoError, "Repositories could not be loaded. Try again."),
          );
        }
      } finally {
        if (latestRepoRequest.current === requestId) {
          setLoadingRepos(false);
        }
      }
    },
    [githubConnected],
  );

  useEffect(() => {
    if (!githubConnected) {
      setRepos([]);
      return;
    }
    const timer = window.setTimeout(() => {
      void loadRepos(repoSearch.trim());
    }, 250);
    return () => window.clearTimeout(timer);
  }, [githubConnected, loadRepos, repoSearch]);

  useEffect(() => {
    if (!selectedRepo) return;
    let cancelled = false;
    setLoadingBranches(true);
    setBranchError(null);

    void api
      .getRepoBranches(selectedRepo.full_name)
      .then((result) => {
        if (cancelled) return;
        const available =
          result.branches.length > 0
            ? result.branches
            : [selectedRepo.default_branch || "main"];
        const defaultBranch = selectedRepo.default_branch || available[0];
        setBranches(available);
        setBranch(available.includes(defaultBranch) ? defaultBranch : available[0]);
      })
      .catch((loadError) => {
        if (cancelled) return;
        const fallback = selectedRepo.default_branch || "main";
        setBranches([fallback]);
        setBranch(fallback);
        setBranchError(
          getErrorMessage(
            loadError,
            `The branch list could not be loaded. ${fallback} is selected from repository metadata.`,
          ),
        );
      })
      .finally(() => {
        if (!cancelled) setLoadingBranches(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedRepo]);

  const resetReview = () => {
    setReview(null);
    setProjectId(null);
    setInfrastructurePlan(null);
    setError(null);
  };

  const chooseRepository = (repo: GitHubRepoItem) => {
    setSelectedRepo(repo);
    setUploadFile(null);
    setSourceName(repo.full_name);
    resetReview();
  };

  const chooseUpload = (file: File | null) => {
    if (!file) {
      setUploadFile(null);
      return;
    }
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setUploadFile(null);
      setError("Only ZIP archives can be uploaded.");
      return;
    }
    setUploadFile(file);
    setSelectedRepo(null);
    setSourceName(file.name);
    resetReview();
  };

  const inspectRepository = async () => {
    if (!selectedRepo) return;
    setIsReviewing(true);
    setError(null);
    try {
      const existingProject = projects.find(
        (project) =>
          project.full_name === selectedRepo.full_name && project.branch === branch,
      );
      const project =
        existingProject ||
        (await api.createProject({
          name: selectedRepo.name,
          full_name: selectedRepo.full_name,
          repo_url: selectedRepo.html_url,
          language: selectedRepo.language || undefined,
          branch,
        }));

      const analysis = await api.analyzeRepo(selectedRepo.full_name, branch);
      const plan = await api.generateInfrastructurePlan(project.id);
      setReview(toReview(analysis));
      setProjectId(project.id);
      setInfrastructurePlan(plan);
      await Promise.all([refreshProjects(), refreshStats()]);
      addToast("A proposed infrastructure plan was generated.", "success");
    } catch (reviewError) {
      setError(
        getErrorMessage(reviewError, "The selected repository could not be reviewed."),
      );
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
      const plan = await api.generateInfrastructurePlan(result.project.id);
      setProjectId(result.project.id);
      setSourceName(uploadFile.name);
      setBranch(result.project.branch || "uploaded");
      setReview(toReview(result.analysis));
      setInfrastructurePlan(plan);
      await Promise.all([refreshProjects(), refreshStats()]);
      addToast("A proposed infrastructure plan was generated.", "success");
    } catch (uploadError) {
      setError(
        getErrorMessage(uploadError, "The ZIP archive could not be processed. Check it and try again."),
      );
    } finally {
      setIsUploading(false);
    }
  };

  const openInfrastructurePlan = () => {
    if (!projectId || !infrastructurePlan) {
      setError("The infrastructure plan response is unavailable. Generate the review again.");
      return;
    }
    router.push(`/dashboard/infrastructure?project=${projectId}`);
  };

  return (
    <div className="mx-auto max-w-5xl pb-10">
      <PageHeader
        eyebrow="New project"
        title="Import application source"
        description="Choose a GitHub repository and branch, or upload a ZIP. ZeroOps will inspect the selected source and generate a plan for your review."
      />

      <nav aria-label="Project import progress" className="mb-6 rounded-xl border border-border bg-card p-3 shadow-sm sm:p-4">
        <ol className="grid gap-2 sm:grid-cols-3">
          {[
            [1, "Choose source", "GitHub or ZIP"],
            [2, "Inspect snapshot", "Repository evidence"],
            [3, "Review plan", "Approval stays separate"],
          ].map(([step, label, detail]) => {
            const stepNumber = Number(step);
            const complete = currentStep > stepNumber;
            const active = currentStep === stepNumber;
            return (
              <li
                key={stepNumber}
                aria-current={active ? "step" : undefined}
                className={`flex items-center gap-3 rounded-lg border px-3 py-3 transition-colors ${
                  active
                    ? "border-primary/30 bg-primary-subtle"
                    : complete
                      ? "border-success/25 bg-success-subtle"
                      : "border-transparent bg-surface-subtle"
                }`}
              >
                <span
                  className={`grid h-8 w-8 shrink-0 place-items-center rounded-full border text-xs font-semibold ${
                    complete
                      ? "border-success/25 bg-card text-success"
                      : active
                        ? "border-primary/25 bg-card text-primary"
                        : "border-border bg-card text-foreground-subtle"
                  }`}
                >
                  {complete ? <CheckCircle2 size={15} aria-hidden="true" /> : stepNumber}
                </span>
                <span className="min-w-0">
                  <span className="block text-xs font-semibold text-foreground">{label}</span>
                  <span className="mt-0.5 block text-[11px] text-foreground-muted">{detail}</span>
                </span>
              </li>
            );
          })}
        </ol>
      </nav>

      {error && (
        <div
          role="alert"
          className="mb-5 flex items-start justify-between gap-3 rounded-xl border border-danger/25 bg-danger-subtle p-4 text-sm leading-5 text-danger"
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            aria-label="Dismiss error"
            className="grid h-10 w-10 shrink-0 place-items-center rounded-lg transition-colors hover:bg-card"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      )}

      {!review ? (
        <div className="space-y-5">
          <section aria-labelledby="source-options-heading">
            <div className="mb-4">
              <p className="text-xs font-semibold uppercase tracking-[0.1em] text-primary">Step one</p>
              <h2 id="source-options-heading" className="mt-1 text-lg font-semibold tracking-tight text-foreground">
                Bring in one source snapshot
              </h2>
              <p className="mt-1 max-w-2xl text-xs leading-5 text-foreground-muted">
                Both paths create the same review flow. Nothing is deployed from this screen.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-border bg-card p-5 shadow-sm transition-[border-color,box-shadow] duration-200 hover:border-border-hover hover:shadow-md sm:p-6">
              <div className="grid h-10 w-10 place-items-center rounded-lg bg-primary-subtle text-primary">
                <GitBranch size={20} aria-hidden="true" />
              </div>
              <h3 className="mt-4 text-base font-semibold text-foreground">GitHub repository</h3>
              <p className="mt-1.5 text-xs leading-5 text-foreground-muted">
                Select one repository and a branch available to the connected GitHub account.
              </p>
              {githubConnected ? (
                <p className="mt-4 flex items-center gap-2 text-xs font-medium text-success">
                  <CheckCircle2 size={15} aria-hidden="true" />
                  Connected{user?.github_username ? ` as @${user.github_username}` : ""}
                </p>
              ) : (
                <button type="button" onClick={loginWithGitHub} className="ops-primary mt-4">
                  Connect GitHub
                </button>
              )}
            </div>

            <div className="rounded-xl border border-border bg-card p-5 shadow-sm transition-[border-color,box-shadow] duration-200 hover:border-border-hover hover:shadow-md sm:p-6">
              <div className="grid h-10 w-10 place-items-center rounded-lg bg-surface-subtle text-foreground">
                <FileArchive size={20} aria-hidden="true" />
              </div>
              <h3 className="mt-4 text-base font-semibold text-foreground">ZIP archive</h3>
              <p className="mt-1.5 text-xs leading-5 text-foreground-muted">
                Upload a source archive. The backend enforces the configured upload size limit and safe extraction checks.
              </p>
              <input
                id="source-zip"
                type="file"
                accept=".zip,application/zip,application/x-zip-compressed"
                className="sr-only"
                onChange={(event) => chooseUpload(event.target.files?.[0] || null)}
              />
              <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                <label htmlFor="source-zip" className="ops-secondary">
                  <Upload size={15} aria-hidden="true" />
                  Choose ZIP
                </label>
                {uploadFile && (
                  <button
                    type="button"
                    onClick={() => void uploadCode()}
                    disabled={isUploading}
                    className="ops-primary min-w-0 flex-1 disabled:opacity-60"
                  >
                    {isUploading ? (
                      <Loader2 size={15} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                    ) : (
                      <ArrowRight size={15} aria-hidden="true" />
                    )}
                    <span className="truncate">
                      {isUploading ? "Processing archive…" : `Review ${uploadFile.name}`}
                    </span>
                  </button>
                )}
              </div>
            </div>
            </div>
          </section>

          {githubConnected && (
            <section
              aria-labelledby="repository-list-heading"
              className="rounded-xl border border-border bg-card p-4 shadow-sm sm:p-5"
            >
              <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <h2 id="repository-list-heading" className="text-base font-semibold text-foreground">
                    Choose a repository
                  </h2>
                  <p className="mt-1 text-xs leading-5 text-foreground-muted">
                    Only the repository selected here is submitted for this review.
                  </p>
                </div>
                <label className="relative block w-full sm:w-72">
                  <span className="sr-only">Search repositories</span>
                  <Search
                    size={15}
                    className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-foreground-subtle"
                    aria-hidden="true"
                  />
                  <input
                    type="search"
                    value={repoSearch}
                    onChange={(event) => setRepoSearch(event.target.value)}
                    placeholder="Search repositories"
                    className="min-h-11 w-full rounded-lg border border-border bg-background-secondary pl-9 pr-3 text-base text-foreground outline-none transition-colors focus:border-primary sm:text-sm"
                  />
                </label>
              </div>

              {loadingRepos ? (
                <div role="status" className="flex min-h-44 items-center justify-center">
                  <Loader2 size={20} className="animate-spin text-primary motion-reduce:animate-none" aria-hidden="true" />
                  <span className="ml-2 text-xs text-foreground-muted">Loading repositories…</span>
                </div>
              ) : repos.length === 0 ? (
                <StatePanel
                  compact
                  title="No repositories found"
                  description={
                    repoSearch
                      ? "No repository matched the current search."
                      : "The connected GitHub account returned no repositories."
                  }
                />
              ) : (
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {repos.map((repo) => {
                    const selected = selectedRepo?.id === repo.id;
                    return (
                      <button
                        key={repo.id}
                        type="button"
                        onClick={() => chooseRepository(repo)}
                        aria-pressed={selected}
                        className={`min-h-28 rounded-lg border p-4 text-left transition-colors ${
                          selected
                            ? "border-primary bg-primary-subtle"
                            : "border-border hover:border-border-hover hover:bg-surface-subtle"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <span className="min-w-0 break-words text-sm font-semibold text-foreground">
                            {repo.name}
                          </span>
                          {selected && (
                            <CheckCircle2
                              size={16}
                              className="shrink-0 text-primary"
                              aria-hidden="true"
                            />
                          )}
                        </div>
                        <p className="mt-1 break-all text-xs text-foreground-muted">
                          {repo.full_name}
                        </p>
                        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-foreground-subtle">
                          <span>{repo.language || "Language not reported"}</span>
                          <span>{sourceDate(repo.updated_at)}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}

              {selectedRepo && (
                <div className="mt-5 rounded-lg border border-border bg-background-secondary p-4">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                    <div className="min-w-0">
                      <p className="break-all text-xs font-semibold text-foreground">
                        {selectedRepo.full_name}
                      </p>
                      <p className="mt-1 text-xs text-foreground-muted">
                        Review will use the branch selected below.
                      </p>
                    </div>
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                      <div>
                        <label htmlFor="repository-branch" className="text-xs font-medium text-foreground">
                          Branch
                        </label>
                        <div className="relative mt-1.5">
                          <select
                            id="repository-branch"
                            value={branch}
                            onChange={(event) => setBranch(event.target.value)}
                            disabled={loadingBranches}
                            className="min-h-11 min-w-40 appearance-none rounded-lg border border-border bg-card py-2 pl-3 pr-9 text-sm font-medium text-foreground outline-none focus:border-primary disabled:opacity-60"
                          >
                            {branches.map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                          <ChevronDown
                            size={14}
                            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-foreground-muted"
                            aria-hidden="true"
                          />
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => void inspectRepository()}
                        disabled={isReviewing || loadingBranches}
                        className="ops-primary disabled:opacity-60"
                      >
                        {isReviewing ? (
                          <>
                            <Loader2 size={15} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                            Reviewing…
                          </>
                        ) : (
                          <>
                            Review source
                            <ArrowRight size={15} aria-hidden="true" />
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                  {branchError && (
                    <p role="status" className="mt-3 text-xs leading-5 text-warning">
                      {branchError}
                    </p>
                  )}
                </div>
              )}
            </section>
          )}
        </div>
      ) : (
        <section aria-labelledby="source-review-heading" className="rounded-xl border border-border bg-card p-5 shadow-sm sm:p-7">
          <div className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-success/25 bg-success-subtle px-2.5 py-1 text-[10px] font-semibold text-success">
                <CheckCircle2 size={12} aria-hidden="true" />
                Plan generated
              </span>
              <h2 id="source-review-heading" className="mt-3 break-words text-xl font-semibold tracking-tight text-foreground">
                {sourceName || "Imported source"}
              </h2>
              <p className="mt-1 text-sm leading-6 text-foreground-muted">
                Repository evidence and a proposed infrastructure plan are ready for review.
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                setReview(null);
                setProjectId(null);
                setInfrastructurePlan(null);
                setError(null);
              }}
              className="ops-secondary shrink-0"
            >
              <ArrowLeft size={15} aria-hidden="true" />
              Change source
            </button>
          </div>

          <dl className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <ReviewFact label="Application type" value={review.applicationType || "Not identified"} />
            <ReviewFact label="Framework" value={review.framework || "Not identified"} />
            <ReviewFact
              label="Target cloud"
              value={infrastructurePlan?.plan.cloud || "Not reported"}
            />
            <ReviewFact
              label="Region"
              value={infrastructurePlan?.plan.region_label || infrastructurePlan?.region || "Not reported"}
            />
          </dl>

          {review.explanation && (
            <div className="mt-4 rounded-lg border border-primary/20 bg-primary-subtle p-4">
              <h2 className="text-xs font-semibold text-primary">Analysis summary</h2>
              <p className="mt-1.5 text-sm leading-6 text-foreground-muted">
                {review.explanation}
              </p>
              <p className="mt-2 text-[11px] leading-5 text-foreground-subtle">
                Confirm this generated summary against the source and plan before approval.
              </p>
            </div>
          )}

          <details className="group mt-4 rounded-lg border border-border bg-surface-subtle">
            <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-xs font-semibold text-foreground [&::-webkit-details-marker]:hidden">
              <span>Environment variable names ({review.environmentVariables.length})</span>
              <ChevronDown size={15} className="transition-transform duration-200 group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
            </summary>
            <div className="border-t border-border px-4 py-4">
              {review.environmentVariables.length > 0 ? (
                <>
                  <p className="text-xs leading-5 text-foreground-muted">
                    Values are not shown here. Add required values through project settings.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {review.environmentVariables.map((variable) => (
                      <code
                        key={variable}
                        className="rounded-md border border-border bg-card px-2 py-1 text-[11px] text-foreground"
                      >
                        {variable}
                      </code>
                    ))}
                  </div>
                </>
              ) : (
                <p className="text-xs leading-5 text-foreground-muted">
                  No environment variable names were found in the analysis response.
                </p>
              )}
            </div>
          </details>

          {infrastructurePlan && (
            <details className="group mt-4 rounded-lg border border-border">
              <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-xs font-semibold text-foreground [&::-webkit-details-marker]:hidden">
                <span>Proposed infrastructure components ({infrastructurePlan.plan.components.length})</span>
                <ChevronDown size={15} className="transition-transform duration-200 group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
              </summary>
              <div className="flex flex-wrap gap-2 border-t border-border p-4">
                {infrastructurePlan.plan.components.length > 0 ? (
                  infrastructurePlan.plan.components.slice(0, 8).map((component) => (
                    <span
                      key={component.id}
                      className="rounded-md border border-border bg-surface-subtle px-2.5 py-1.5 text-xs font-medium text-foreground"
                    >
                      {component.service}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-foreground-muted">
                    No components were returned.
                  </span>
                )}
              </div>
            </details>
          )}

          <div className="mt-6 flex flex-col gap-4 rounded-xl border border-success/25 bg-success-subtle p-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex gap-3">
              <ShieldCheck
                size={20}
                className="mt-0.5 shrink-0 text-success"
                aria-hidden="true"
              />
              <div>
                <h2 className="text-sm font-semibold text-foreground">
                  Approval is required before deployment
                </h2>
                <p className="mt-1 text-xs leading-5 text-foreground-muted">
                  Review resource choices, unresolved questions, and cost-validation status in the plan.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={openInfrastructurePlan}
              disabled={!infrastructurePlan}
              className="ops-primary shrink-0 disabled:opacity-60"
            >
              Review infrastructure plan
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

function ReviewFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface-subtle p-4">
      <dt className="text-[10px] font-semibold uppercase tracking-wide text-foreground-muted">
        {label}
      </dt>
      <dd className="mt-2 break-words text-sm font-semibold text-foreground">{value}</dd>
    </div>
  );
}
