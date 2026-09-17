import Link from "next/link";
import {
  ArrowRight,
  Check,
  Cloud,
  FileSearch,
  GitBranch,
  ListChecks,
  LockKeyhole,
  ShieldCheck,
} from "lucide-react";
import { HomeHeroMotion } from "@/components/landing/HomeHeroMotion";
import { PublicFooter } from "@/components/public/PublicFooter";
import { PublicHeader } from "@/components/public/PublicHeader";

const mvpCapabilities = [
  {
    status: "available",
    statusLabel: "Available",
    title: "Understand the source",
    description:
      "Select a GitHub repository and branch for the release flow, or upload a ZIP for analysis only. ZeroOps records bounded facts such as framework, runtime, commands, and environment-key names.",
    note: "Secret values are never part of repository evidence.",
    icon: FileSearch,
  },
  {
    status: "available",
    statusLabel: "Available",
    title: "See every gate clearly",
    description:
      "Relevant pipeline and security stages keep an explicit outcome: succeeded, failed, skipped, blocked, or unavailable. A missing required tool does not become a pass.",
    note: "Every recorded outcome includes a reason and supporting evidence.",
    icon: ListChecks,
  },
  {
    status: "setup_required",
    statusLabel: "Setup required",
    title: "Approve the exact release",
    description:
      "Approval is bound to the commit, target, plan, and configuration. After approval, a configured worker can queue the locally tested Azure App Service release path.",
    note: "Azure and worker prerequisites must be connected before execution.",
    icon: LockKeyhole,
  },
] as const;

const workflow = [
  {
    number: "01",
    title: "Connect",
    description:
      "Choose the repository, branch, and App Service target you intend to review.",
    icon: GitBranch,
  },
  {
    number: "02",
    title: "Inspect",
    description:
      "Review source facts and each applicable check with its real recorded state.",
    icon: ShieldCheck,
  },
  {
    number: "03",
    title: "Decide",
    description:
      "Approve or reject the exact release. Required approval keeps execution locked.",
    icon: Cloud,
  },
] as const;

const proofPoints = [
  "Commit-pinned runs",
  "Missing checks block",
  "No synthetic telemetry",
] as const;

function CapabilityCard({
  capability,
  index,
}: {
  capability: (typeof mvpCapabilities)[number];
  index: number;
}) {
  const Icon = capability.icon;
  const needsSetup = capability.status === "setup_required";

  return (
    <article
      className="group relative flex h-full flex-col overflow-hidden rounded-xl p-6 transition-all duration-200 hover:-translate-y-1 sm:p-7"
      style={{ border: "1px solid var(--border)", background: "var(--card)", boxShadow: "var(--shadow-sm)" }}
    >
      <div
        aria-hidden="true"
        className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-blue-500/40 to-transparent opacity-0 transition-opacity duration-200 group-hover:opacity-100"
      />

      <div className="flex items-start justify-between gap-4">
        <span
          className="grid h-11 w-11 place-items-center rounded-xl shadow-sm"
          style={{ border: "1px solid var(--primary-subtle)", background: "var(--primary-subtle)", color: "var(--primary)" }}
        >
          <Icon aria-hidden="true" size={19} />
        </span>
        <span
          className={[
            "inline-flex min-h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-semibold",
            needsSetup
              ? "border-amber-500/30 bg-amber-500/10 text-amber-600"
              : "border-emerald-500/30 bg-emerald-500/10 text-emerald-700",
          ].join(" ")}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${needsSetup ? "bg-amber-500" : "bg-emerald-600"}`} />
          {capability.statusLabel}
        </span>
      </div>

      <p className="mt-7 font-mono text-xs font-semibold" style={{ color: "var(--primary)" }}>
        0{index + 1}
      </p>
      <h3 className="mt-2 text-xl font-semibold tracking-[-0.025em]" style={{ color: "var(--foreground)" }}>
        {capability.title}
      </h3>
      <p className="mt-3 text-sm leading-6" style={{ color: "var(--foreground-subtle)" }}>
        {capability.description}
      </p>
      <p className="mt-6 pt-4 text-xs leading-5" style={{ borderTop: "1px solid var(--border)", color: "var(--foreground-subtle)" }}>
        {capability.note}
      </p>
    </article>
  );
}

function WorkflowStep({
  step,
  index,
}: {
  step: (typeof workflow)[number];
  index: number;
}) {
  const Icon = step.icon;

  return (
    <li className="relative grid grid-cols-[3rem_minmax(0,1fr)] gap-4 lg:grid-cols-1 lg:gap-0">
      {index < workflow.length - 1 ? (
        <span
          aria-hidden="true"
          className="absolute left-6 top-12 h-[calc(100%-1rem)] w-px lg:left-[calc(50%+1.5rem)] lg:top-6 lg:h-px lg:w-[calc(100%-3rem)]"
          style={{ background: "var(--border)" }}
        />
      ) : null}

      <span
        className="relative z-10 grid h-12 w-12 place-items-center rounded-xl shadow-sm lg:mx-auto"
        style={{ border: "1px solid var(--primary-subtle)", background: "var(--surface-subtle)", color: "var(--primary)" }}
      >
        <Icon aria-hidden="true" size={19} />
      </span>
      <div className="pb-8 lg:pb-0 lg:pt-6 lg:text-center">
        <p className="font-mono text-xs font-semibold" style={{ color: "var(--primary)" }}>
          Step {step.number}
        </p>
        <h3 className="mt-2 text-lg font-semibold" style={{ color: "var(--foreground)" }}>{step.title}</h3>
        <p className="mx-auto mt-2 max-w-sm text-sm leading-6" style={{ color: "var(--foreground-subtle)" }}>
          {step.description}
        </p>
      </div>
    </li>
  );
}

export function MarketingHome() {
  return (
    <div className="min-h-dvh" style={{ background: "var(--background)", color: "var(--foreground)" }}>
      <PublicHeader />

      <main id="main-content">
        <section className="relative overflow-hidden" style={{ borderBottom: "1px solid var(--border)" }}>
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 opacity-30 [mask-image:linear-gradient(to_bottom,black,transparent_82%)]"
            style={{ backgroundImage: "radial-gradient(var(--border) 1px,transparent 1px)", backgroundSize: "24px 24px" }}
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute left-[15%] top-8 h-96 w-96 rounded-full blur-3xl"
            style={{ background: "var(--primary-subtle)" }}
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute right-[10%] top-24 h-80 w-80 rounded-full blur-3xl"
            style={{ background: "var(--success-subtle)" }}
          />

          <div className="relative mx-auto grid w-full max-w-7xl gap-12 px-4 py-14 sm:px-6 sm:py-20 lg:grid-cols-[1.02fr_.98fr] lg:items-center lg:gap-16 lg:px-8 lg:py-24">
            <div>
              <div
                className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold"
                style={{ border: "1px solid var(--primary-subtle)", background: "var(--primary-subtle)", color: "var(--primary)", boxShadow: "var(--shadow-glow-blue)" }}
              >
                <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
                Azure App Service · Deployment Platform
              </div>

              <h1 className="mt-7 max-w-3xl text-balance text-5xl font-bold leading-[1.02] tracking-tight sm:text-6xl lg:text-7xl" style={{ color: "var(--foreground)" }}>
                See what will happen before a release reaches Azure.
              </h1>
              <p className="mt-6 max-w-2xl text-pretty text-base leading-7 sm:text-lg sm:leading-8" style={{ color: "var(--foreground-subtle)" }}>
                Create a commit-pinned release record, inspect every recorded
                validation outcome, and approve the exact plan. Missing tools,
                telemetry, or cloud prerequisites stay visibly unavailable.
              </p>

              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Link
                  href="/signup"
                  className="group inline-flex min-h-12 items-center justify-center gap-2 rounded-lg bg-blue-600 px-5 text-sm font-semibold text-white shadow-lg shadow-blue-500/25 transition-all duration-150 hover:bg-blue-500 active:scale-[0.99] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
                >
                  Create a workspace
                  <ArrowRight
                    aria-hidden="true"
                    size={16}
                    className="transition-transform duration-200 group-hover:translate-x-0.5"
                  />
                </Link>
                <a
                  href="#capabilities"
                  className="inline-flex min-h-12 items-center justify-center rounded-lg px-5 text-sm font-semibold transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                  style={{ border: "1px solid var(--border)", background: "var(--card)", color: "var(--foreground)" }}
                >
                  See what works today
                </a>
              </div>

              <ul
                aria-label="MVP evidence principles"
                className="mt-7 flex flex-wrap gap-x-5 gap-y-3 text-sm"
                style={{ color: "var(--foreground-subtle)" }}
              >
                {proofPoints.map((item) => (
                  <li key={item} className="inline-flex items-center gap-2">
                    <Check
                      aria-hidden="true"
                      size={15}
                      strokeWidth={2.5}
                      className="text-emerald-600"
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
          id="capabilities"
          className="scroll-mt-20"
          style={{ borderBottom: "1px solid var(--border)", background: "var(--background-secondary)" }}
        >
          <div className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8 lg:py-24">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
              <div className="max-w-3xl">
                <p className="text-xs font-semibold uppercase tracking-[0.16em]" style={{ color: "var(--primary)" }}>
                  Platform capabilities
                </p>
                <h2 className="mt-3 text-balance text-3xl font-bold tracking-tight sm:text-4xl" style={{ color: "var(--foreground)" }}>
                  Three capabilities. Each with verifiable evidence.
                </h2>
              </div>
              <p className="max-w-xl text-sm leading-6 lg:text-right" style={{ color: "var(--foreground-subtle)" }}>
                ZeroOps keeps the release decision understandable. It records
                evidence, refuses to turn missing checks into green states,
                and leaves cloud execution behind explicit prerequisites.
              </p>
            </div>

            <div className="mt-10 grid gap-5 lg:grid-cols-3">
              {mvpCapabilities.map((capability, index) => (
                <CapabilityCard
                  key={capability.title}
                  capability={capability}
                  index={index}
                />
              ))}
            </div>
          </div>
        </section>

        <section id="workflow" className="scroll-mt-20" style={{ borderBottom: "1px solid var(--border)", background: "var(--background)" }}>
          <div className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8 lg:py-24">
            <div className="mx-auto max-w-3xl text-left sm:text-center">
              <p className="text-xs font-semibold uppercase tracking-[0.16em]" style={{ color: "var(--primary)" }}>
                One focused workflow
              </p>
              <h2 className="mt-3 text-balance text-3xl font-bold tracking-tight sm:text-4xl" style={{ color: "var(--foreground)" }}>
                Connect the source. Inspect the gates. Make the decision.
              </h2>
              <p className="mt-4 text-base leading-7" style={{ color: "var(--foreground-subtle)" }}>
                Designed around a review-first App Service path with
                commit-pinned evidence at every stage.
              </p>
            </div>

            <ol
              aria-label="ZeroOps MVP workflow"
              className="mt-12 grid gap-0 lg:grid-cols-3 lg:gap-10"
            >
              {workflow.map((step, index) => (
                <WorkflowStep key={step.number} step={step} index={index} />
              ))}
            </ol>
          </div>
        </section>

        <section style={{ background: "var(--background-secondary)" }}>
          <div className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
            <div
              className="relative overflow-hidden rounded-2xl p-7 sm:p-10 lg:p-12"
              style={{ border: "1px solid var(--border)", background: "var(--card)", boxShadow: "var(--shadow-lg)" }}
            >
              <div
                aria-hidden="true"
                className="pointer-events-none absolute -right-24 -top-32 h-80 w-80 rounded-full blur-3xl"
                style={{ background: "var(--primary-subtle)" }}
              />
              <div
                aria-hidden="true"
                className="pointer-events-none absolute -left-24 -bottom-32 h-80 w-80 rounded-full blur-3xl"
                style={{ background: "var(--success-subtle)" }}
              />

              <div className="relative grid gap-9 lg:grid-cols-[1fr_auto] lg:items-end lg:gap-12">
                <div className="max-w-3xl">
                  <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em]" style={{ color: "var(--success)" }}>
                    <ShieldCheck aria-hidden="true" size={15} />
                    Honest by design
                  </div>
                  <h2 className="mt-3 text-balance text-3xl font-bold tracking-tight sm:text-4xl" style={{ color: "var(--foreground)" }}>
                    Start with what is ready. Keep the rest visibly gated.
                  </h2>
                  <p className="mt-4 max-w-2xl text-sm leading-6 sm:text-base sm:leading-7" style={{ color: "var(--foreground-subtle)" }}>
                    Additional Azure targets and managed telemetry collection
                    are on the roadmap. Recorded logs and monitoring appear
                    only when real data exists.
                  </p>

                  <div className="mt-6 flex flex-wrap gap-x-6 gap-y-1 text-sm">
                    <Link
                      href="/docs"
                      className="inline-flex min-h-11 items-center font-semibold transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                      style={{ color: "var(--primary)" }}
                    >
                      Read the documentation
                    </Link>
                    <Link
                      href="/status"
                      className="inline-flex min-h-11 items-center font-semibold transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                      style={{ color: "var(--foreground-subtle)" }}
                    >
                      View service status
                    </Link>
                  </div>
                </div>

                <Link
                  href="/signup"
                  className="group inline-flex min-h-12 shrink-0 items-center justify-center gap-2 rounded-lg bg-blue-600 px-5 text-sm font-semibold text-white shadow-lg shadow-blue-500/25 transition-all duration-150 hover:bg-blue-500 active:scale-[0.99] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
                >
                  Create a workspace
                  <ArrowRight
                    aria-hidden="true"
                    size={16}
                    className="transition-transform duration-200 group-hover:translate-x-0.5"
                  />
                </Link>
              </div>
            </div>
          </div>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}
