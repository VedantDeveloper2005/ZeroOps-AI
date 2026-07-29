import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Check,
  CheckCircle2,
  CircleDollarSign,
  Cloud,
  Code2,
  FileArchive,
  FileSearch,
  GitBranch,
  HardDrive,
  ListChecks,
  LockKeyhole,
  Minus,
  Route,
  Server,
  ShieldCheck,
  SquareTerminal,
  type LucideIcon,
} from "lucide-react";
import { HomeHeroMotion } from "@/components/landing/HomeHeroMotion";
import { PublicFooter } from "@/components/public/PublicFooter";
import { PublicHeader } from "@/components/public/PublicHeader";

const workflow = [
  {
    number: "01",
    title: "Choose your source",
    description:
      "Connect a GitHub repository and branch for the review-and-deploy workflow, or upload a ZIP for analysis only.",
    icon: GitBranch,
  },
  {
    number: "02",
    title: "Review repository evidence",
    description:
      "Deterministic inspection records the framework, runtime, commands, environment keys, and deployment requirements it can establish.",
    icon: FileSearch,
  },
  {
    number: "03",
    title: "Inspect the Azure plan",
    description:
      "Review an Azure App Service plan with its region, tier, supporting resources, reasoning, and estimated monthly cost.",
    icon: ListChecks,
  },
  {
    number: "04",
    title: "Approve, then deploy",
    description:
      "For GitHub-backed projects, approval unlocks the deployment action and queues the plan for the dedicated worker.",
    icon: Cloud,
  },
] as const;

const repositoryEvidence = [
  "Framework, language, and runtime",
  "Package manager and dependency names",
  "Build command, start command, and port",
  "Environment-variable names, never secret values",
  "Database and deployment requirements",
] as const;

const planRows = [
  {
    label: "Deployment target",
    value: "Azure App Service",
    detail: "Current deployable provider",
    icon: Cloud,
  },
  {
    label: "Region and tier",
    value: "Selected before approval",
    detail: "Change returns the plan to draft",
    icon: Server,
  },
  {
    label: "Monthly cost",
    value: "Estimate shown in the plan",
    detail: "Final Azure billing can differ",
    icon: CircleDollarSign,
  },
  {
    label: "Deployment state",
    value: "Locked until approved",
    detail: "Starting the job remains explicit",
    icon: LockKeyhole,
  },
] as const;

const executionPath = [
  {
    title: "Control plane",
    description: "Records the approved specification and deployment request.",
    icon: Code2,
  },
  {
    title: "PostgreSQL queue",
    description: "Keeps the job available for the deployment worker to claim.",
    icon: HardDrive,
  },
  {
    title: "Dedicated worker",
    description: "Runs Azure build and App Service deployment stages outside the API.",
    icon: Server,
  },
  {
    title: "Your Azure target",
    description: "Receives the approved App Service resources and application.",
    icon: Cloud,
  },
] as const;

const currentCapabilities = [
  "GitHub repository intake for review and deployment",
  "ZIP intake for analysis only until durable worker-accessible storage is configured",
  "Deterministic repository inspection with optional AI-enriched explanation",
  "Versioned, approval-based Azure App Service infrastructure plans",
  "Queued Azure App Service deployment execution in a dedicated worker",
  "Deployment logs and project metrics when records exist",
] as const;

const notClaimed = [
  "Separate analysis, security-scanning, monitoring, CI/CD, or remediation workers",
  "Automatic code changes or hidden infrastructure changes",
  "Compliance certification or continuous security assurance",
  "Guaranteed telemetry, uptime, deployment success, or exact cloud cost",
] as const;

function WorkflowCard({
  item,
}: {
  item: (typeof workflow)[number];
}) {
  const Icon = item.icon;

  return (
    <li className="relative border-t border-border pt-6">
      <div className="flex items-center justify-between gap-4">
        <span className="font-mono text-xs font-semibold text-foreground-subtle">
          {item.number}
        </span>
        <span className="grid h-10 w-10 place-items-center rounded-xl border border-border bg-card text-primary shadow-sm">
          <Icon aria-hidden="true" size={18} />
        </span>
      </div>
      <h3 className="mt-7 text-lg font-semibold tracking-[-0.02em]">
        {item.title}
      </h3>
      <p className="mt-2 text-sm leading-6 text-foreground-muted">
        {item.description}
      </p>
    </li>
  );
}

function PlanRow({
  item,
}: {
  item: (typeof planRows)[number];
}) {
  const Icon = item.icon;

  return (
    <li className="grid gap-3 border-b border-border py-4 last:border-b-0 sm:grid-cols-[1fr_1.35fr] sm:items-center">
      <div className="flex items-center gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-primary-subtle text-primary">
          <Icon aria-hidden="true" size={17} />
        </span>
        <span className="text-sm font-medium text-foreground-muted">
          {item.label}
        </span>
      </div>
      <div className="pl-12 sm:pl-0">
        <p className="text-sm font-semibold text-foreground">{item.value}</p>
        <p className="mt-0.5 text-xs leading-5 text-foreground-muted">
          {item.detail}
        </p>
      </div>
    </li>
  );
}

function ExecutionStep({
  item,
  index,
}: {
  item: (typeof executionPath)[number];
  index: number;
}) {
  const Icon = item.icon;

  return (
    <li className="relative flex gap-4 lg:min-w-0 lg:flex-1 lg:flex-col">
      <div className="relative z-10 grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-primary/25 bg-background text-primary shadow-sm">
        <Icon aria-hidden="true" size={19} />
      </div>
      <div className="pb-7 lg:pb-0">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-foreground-subtle">
          Stage {index + 1}
        </p>
        <h3 className="mt-2 text-base font-semibold">{item.title}</h3>
        <p className="mt-1.5 text-sm leading-6 text-foreground-muted">
          {item.description}
        </p>
      </div>
    </li>
  );
}

function DataSurface({
  icon: Icon,
  title,
  availability,
  description,
  emptyState,
}: {
  icon: LucideIcon;
  title: string;
  availability: string;
  description: string;
  emptyState: string;
}) {
  return (
    <article className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-primary-subtle text-primary">
          <Icon aria-hidden="true" size={18} />
        </span>
        <span className="rounded-full border border-border bg-surface-subtle px-2.5 py-1 text-[11px] font-semibold text-foreground-muted">
          {availability}
        </span>
      </div>
      <h3 className="mt-6 text-lg font-semibold">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-foreground-muted">
        {description}
      </p>
      <div className="mt-5 rounded-xl border border-dashed border-border bg-background p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-foreground-subtle">
          Honest empty state
        </p>
        <p className="mt-2 text-sm leading-6 text-foreground-muted">
          {emptyState}
        </p>
      </div>
    </article>
  );
}

function BoundaryList({
  title,
  items,
  tone,
}: {
  title: string;
  items: readonly string[];
  tone: "available" | "limited";
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <ul className="mt-4 space-y-3">
        {items.map((item) => (
          <li
            key={item}
            className="flex gap-3 text-sm leading-6 text-foreground-muted"
          >
            <span
              className={[
                "mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full",
                tone === "available"
                  ? "bg-success-subtle text-success"
                  : "bg-surface-raised text-foreground-subtle",
              ].join(" ")}
            >
              {tone === "available" ? (
                <Check aria-hidden="true" size={12} strokeWidth={2.5} />
              ) : (
                <Minus aria-hidden="true" size={12} strokeWidth={2.5} />
              )}
            </span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function MarketingHome() {
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <PublicHeader current="home" />

      <main id="main-content">
        <section className="relative overflow-hidden border-b border-border">
          <div
            aria-hidden="true"
            className="ops-page-grid pointer-events-none absolute inset-0 opacity-40 [mask-image:linear-gradient(to_bottom,black,transparent_78%)]"
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute left-1/2 top-0 h-72 w-[48rem] -translate-x-1/2 rounded-full bg-primary-glow blur-3xl"
          />

          <div className="relative mx-auto grid w-full max-w-7xl gap-12 px-4 py-16 sm:px-6 sm:py-20 lg:grid-cols-[1.02fr_.98fr] lg:items-center lg:gap-16 lg:px-8 lg:py-24">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground-muted shadow-sm">
                <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                Current deployable target: Azure App Service
              </div>

              <h1 className="mt-7 max-w-3xl text-balance text-5xl font-semibold leading-[1.02] tracking-[-0.06em] sm:text-6xl lg:text-7xl">
                From source code to a reviewable Azure deployment.
              </h1>
              <p className="mt-6 max-w-2xl text-pretty text-base leading-7 text-foreground-muted sm:text-lg sm:leading-8">
                Import a GitHub repository, inspect deterministic deployment
                evidence, approve the App Service plan, and send it to a
                dedicated worker. ZIP uploads support analysis only today.
              </p>

              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Link
                  href="/signup"
                  className="group inline-flex min-h-12 items-center justify-center gap-2 rounded-lg bg-primary px-5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  Start with your source
                  <ArrowRight
                    aria-hidden="true"
                    size={16}
                    className="transition-transform group-hover:translate-x-0.5"
                  />
                </Link>
                <a
                  href="#workflow"
                  className="inline-flex min-h-12 items-center justify-center rounded-lg border border-border bg-card px-5 text-sm font-semibold text-foreground transition-colors hover:border-border-hover hover:bg-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  See the workflow
                </a>
              </div>

              <ul
                aria-label="Workflow guarantees"
                className="mt-7 flex flex-wrap gap-x-5 gap-y-3 text-sm text-foreground-muted"
              >
                {[
                  "No deployment before approval",
                  "Cloud actions stay behind approval",
                  "No invented telemetry",
                ].map((item) => (
                  <li key={item} className="inline-flex items-center gap-2">
                    <CheckCircle2
                      aria-hidden="true"
                      size={15}
                      className="text-success"
                    />
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            <HomeHeroMotion />
          </div>
        </section>

        <section
          id="workflow"
          className="scroll-mt-20 border-b border-border bg-card/35"
        >
          <div className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
                The current workflow
              </p>
              <h2 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.045em] sm:text-4xl">
                Four clear stages. Two explicit decisions.
              </h2>
              <p className="mt-4 max-w-2xl text-base leading-7 text-foreground-muted">
                You choose the source and you authorize the deployment. ZeroOps
                structures the evidence and execution path between those
                decisions.
              </p>
            </div>

            <ol className="mt-10 grid gap-x-7 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
              {workflow.map((item) => (
                <WorkflowCard key={item.number} item={item} />
              ))}
            </ol>
          </div>
        </section>

        <section
          id="analysis"
          className="scroll-mt-20 border-b border-border"
        >
          <div className="mx-auto grid w-full max-w-7xl gap-12 px-4 py-16 sm:px-6 sm:py-20 lg:grid-cols-[.88fr_1.12fr] lg:items-center lg:gap-20 lg:px-8 lg:py-24">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
                Repository evidence
              </p>
              <h2 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.045em] sm:text-4xl">
                Start from what the repository can prove.
              </h2>
              <p className="mt-5 text-base leading-7 text-foreground-muted">
                ZeroOps reads the source you select and records deployment
                facts. GitHub-backed source can continue to the worker;
                uploaded ZIP source remains analysis-only until durable shared
                storage is configured. A model can enrich the explanation when
                configured.
              </p>
              <div className="mt-7 rounded-xl border border-border bg-surface-subtle p-4 text-sm leading-6 text-foreground-muted">
                <strong className="font-semibold text-foreground">
                  Scope boundary:
                </strong>{" "}
                this analysis is not presented as a separate security-scanning
                worker, compliance review, or automated code-remediation
                service.
              </div>
            </div>

            <div className="rounded-2xl border border-border bg-card shadow-sm">
              <div className="flex items-center gap-3 border-b border-border px-5 py-4">
                <span className="grid h-9 w-9 place-items-center rounded-lg bg-primary-subtle text-primary">
                  <FileArchive aria-hidden="true" size={17} />
                </span>
                <div>
                  <p className="text-sm font-semibold">Repository evidence</p>
                  <p className="mt-0.5 text-xs text-foreground-muted">
                    Derived from the selected repository or archive
                  </p>
                </div>
              </div>
              <ul className="divide-y divide-border px-5">
                {repositoryEvidence.map((item) => (
                  <li
                    key={item}
                    className="flex items-center gap-3 py-4 text-sm text-foreground"
                  >
                    <Check
                      aria-hidden="true"
                      size={15}
                      className="shrink-0 text-success"
                    />
                    {item}
                  </li>
                ))}
              </ul>
              <div className="border-t border-border bg-background-secondary/60 px-5 py-4">
                <p className="flex gap-2 text-xs leading-5 text-foreground-muted">
                  <ShieldCheck
                    aria-hidden="true"
                    size={15}
                    className="mt-0.5 shrink-0 text-primary"
                  />
                  Secret values belong in authenticated runtime configuration,
                  not in source code or analysis output.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section
          id="approval"
          className="scroll-mt-20 border-b border-border bg-card/35"
        >
          <div className="mx-auto grid w-full max-w-7xl gap-12 px-4 py-16 sm:px-6 sm:py-20 lg:grid-cols-[.82fr_1.18fr] lg:items-start lg:gap-20 lg:px-8 lg:py-24">
            <div className="lg:sticky lg:top-28">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
                Approval boundary
              </p>
              <h2 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.045em] sm:text-4xl">
                The plan is a decision record, not a hidden cloud action.
              </h2>
              <p className="mt-5 text-base leading-7 text-foreground-muted">
                The deployable plan is intentionally narrow today: Azure App
                Service. You can review its reasoning and cost estimate before
                approval.
              </p>
              <p className="mt-4 text-sm leading-6 text-foreground-muted">
                Change the region, tier, or resource specification and the plan
                returns to draft. Approval is required again before another
                deployment can begin.
              </p>
              <Link
                href="/docs#plan"
                className="group mt-7 inline-flex min-h-11 items-center gap-2 rounded-lg text-sm font-semibold text-primary transition-colors hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                Read the plan workflow
                <ArrowRight
                  aria-hidden="true"
                  size={15}
                  className="transition-transform group-hover:translate-x-0.5"
                />
              </Link>
            </div>

            <div className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-7">
              <div className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-foreground-subtle">
                    Infrastructure plan
                  </p>
                  <h3 className="mt-2 text-xl font-semibold">
                    Review before provisioning
                  </h3>
                </div>
                <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-warning/25 bg-warning-subtle px-2.5 py-1 text-xs font-semibold text-warning">
                  <LockKeyhole aria-hidden="true" size={13} />
                  Draft
                </span>
              </div>
              <ul>
                {planRows.map((item) => (
                  <PlanRow key={item.label} item={item} />
                ))}
              </ul>
              <div className="mt-4 rounded-xl bg-foreground p-4 text-background sm:flex sm:items-center sm:justify-between sm:gap-5">
                <div>
                  <p className="text-sm font-semibold">Approval remains human</p>
                  <p className="mt-1 text-xs leading-5 opacity-75">
                    The backend rejects deployment requests without an approved
                    plan.
                  </p>
                </div>
                <span className="mt-3 inline-flex min-h-10 items-center rounded-lg border border-background/25 px-3 text-xs font-semibold sm:mt-0">
                  Review required
                </span>
              </div>
            </div>
          </div>
        </section>

        <section
          id="execution"
          className="scroll-mt-20 border-b border-border"
        >
          <div className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8 lg:py-24">
            <div className="grid gap-8 lg:grid-cols-[1fr_.8fr] lg:items-end">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
                  Execution plane
                </p>
                <h2 className="mt-3 max-w-3xl text-balance text-3xl font-semibold tracking-[-0.045em] sm:text-4xl">
                  Privileged deployment work leaves the API request path.
                </h2>
              </div>
              <p className="text-base leading-7 text-foreground-muted">
                An approved job is stored in the queue, claimed by the dedicated
                worker, and reported back as deployment stages and logs.
              </p>
            </div>

            <ol
              aria-label="Approved deployment execution path"
              className="relative mt-12 space-y-0 before:absolute before:bottom-7 before:left-[1.34rem] before:top-7 before:w-px before:bg-border lg:flex lg:gap-6 lg:before:bottom-auto lg:before:left-8 lg:before:right-8 lg:before:top-[1.34rem] lg:before:h-px lg:before:w-auto"
            >
              {executionPath.map((item, index) => (
                <ExecutionStep
                  key={item.title}
                  item={item}
                  index={index}
                />
              ))}
            </ol>

            <div className="mt-10 flex gap-3 rounded-xl border border-border bg-surface-subtle p-4 text-sm leading-6 text-foreground-muted">
              <Route
                aria-hidden="true"
                size={18}
                className="mt-0.5 shrink-0 text-primary"
              />
              <p>
                This isolation claim applies to the application deployment
                worker. ZeroOps does not present analysis, security,
                monitoring, or remediation as separate worker services today.
              </p>
            </div>
          </div>
        </section>

        <section
          id="operations"
          className="scroll-mt-20 border-b border-border bg-card/35"
        >
          <div className="mx-auto grid w-full max-w-7xl gap-12 px-4 py-16 sm:px-6 sm:py-20 lg:grid-cols-[.72fr_1.28fr] lg:gap-16 lg:px-8 lg:py-24">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
                After deployment
              </p>
              <h2 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.045em] sm:text-4xl">
                Operational views follow the data.
              </h2>
              <p className="mt-5 text-base leading-7 text-foreground-muted">
                ZeroOps does not turn missing records into reassuring charts.
                Logs and monitoring appear when the deployment workflow and
                telemetry path have produced them.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <DataSurface
                icon={SquareTerminal}
                title="Deployment logs"
                availability="When recorded"
                description="Read stored deployment output and receive best-effort live WebSocket updates while the worker reports progress."
                emptyState="No deployment logs are available for this project yet."
              />
              <DataSurface
                icon={Activity}
                title="Project monitoring"
                availability="When available"
                description="Read response time, availability, request, error, CPU, and memory records returned by the project metrics API."
                emptyState="Deploy an application and connect telemetry to see monitoring data."
              />
            </div>
          </div>
        </section>

        <section id="scope" className="scroll-mt-20 border-b border-border">
          <div className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
                Product scope
              </p>
              <h2 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.045em] sm:text-4xl">
                Trust starts with an accurate boundary.
              </h2>
              <p className="mt-4 text-base leading-7 text-foreground-muted">
                The public product should be no broader than the software behind
                it. These are the claims this MVP can—and cannot—make.
              </p>
            </div>

            <div className="mt-10 grid gap-10 rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8 lg:grid-cols-2 lg:gap-14">
              <BoundaryList
                title="Available in the current workflow"
                items={currentCapabilities}
                tone="available"
              />
              <BoundaryList
                title="Not presented as implemented"
                items={notClaimed}
                tone="limited"
              />
            </div>

            <div className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-sm">
              <Link
                href="/security"
                className="inline-flex min-h-11 items-center text-primary transition-colors hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                Security implementation overview
              </Link>
              <Link
                href="/data-processing"
                className="inline-flex min-h-11 items-center text-primary transition-colors hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                Data processing details
              </Link>
              <Link
                href="/status"
                className="inline-flex min-h-11 items-center text-primary transition-colors hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                Public status boundary
              </Link>
            </div>
          </div>
        </section>

        <section className="bg-card/35">
          <div className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
            <div className="rounded-3xl border border-primary/20 bg-primary-subtle p-7 sm:p-10 lg:flex lg:items-center lg:justify-between lg:gap-12">
              <div className="max-w-3xl">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
                  Start with evidence
                </p>
                <h2 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">
                  Bring the source. Keep the deployment decision.
                </h2>
                <p className="mt-4 max-w-2xl text-sm leading-6 text-foreground-muted">
                  Create a workspace and select a GitHub repository for the
                  review-and-deploy workflow, or upload a ZIP for analysis
                  only. Azure actions remain explicit.
                </p>
              </div>
              <Link
                href="/signup"
                className="group mt-7 inline-flex min-h-12 shrink-0 items-center justify-center gap-2 rounded-lg bg-primary px-5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-primary-subtle lg:mt-0"
              >
                Create your workspace
                <ArrowRight
                  aria-hidden="true"
                  size={16}
                  className="transition-transform group-hover:translate-x-0.5"
                />
              </Link>
            </div>
          </div>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}
