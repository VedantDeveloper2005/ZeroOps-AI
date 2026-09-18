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
  Zap,
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
    gradient: "from-blue-500/20 to-indigo-500/20",
    iconColor: "text-blue-400",
    borderColor: "border-blue-500/20",
  },
  {
    status: "available",
    statusLabel: "Available",
    title: "See every gate clearly",
    description:
      "Relevant pipeline and security stages keep an explicit outcome: succeeded, failed, skipped, blocked, or unavailable. A missing required tool does not become a pass.",
    note: "Every recorded outcome includes a reason and supporting evidence.",
    icon: ListChecks,
    gradient: "from-emerald-500/20 to-cyan-500/20",
    iconColor: "text-emerald-400",
    borderColor: "border-emerald-500/20",
  },
  {
    status: "setup_required",
    statusLabel: "Setup required",
    title: "Approve the exact release",
    description:
      "Approval is bound to the commit, target, plan, and configuration. After approval, a configured worker can queue the locally tested Azure App Service release path.",
    note: "Azure and worker prerequisites must be connected before execution.",
    icon: LockKeyhole,
    gradient: "from-amber-500/20 to-orange-500/20",
    iconColor: "text-amber-400",
    borderColor: "border-amber-500/20",
  },
] as const;

const workflow = [
  {
    number: "01",
    title: "Connect",
    description:
      "Choose the repository, branch, and App Service target you intend to review.",
    icon: GitBranch,
    color: "text-blue-400",
    bg: "bg-blue-500/10",
    border: "border-blue-500/20",
  },
  {
    number: "02",
    title: "Inspect",
    description:
      "Review source facts and each applicable check with its real recorded state.",
    icon: ShieldCheck,
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/20",
  },
  {
    number: "03",
    title: "Decide",
    description:
      "Approve or reject the exact release. Required approval keeps execution locked.",
    icon: Cloud,
    color: "text-violet-400",
    bg: "bg-violet-500/10",
    border: "border-violet-500/20",
  },
] as const;

const proofPoints = [
  "Commit-pinned runs",
  "Missing checks block",
  "No synthetic telemetry",
] as const;

const metrics = [
  { value: "12", label: "Pipeline stages", sublabel: "per deployment" },
  { value: "3", label: "Security scanners", sublabel: "Gitleaks · Semgrep · Trivy" },
  { value: "100%", label: "Evidence recorded", sublabel: "no mock data" },
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
    <article className="zo-glow-card group flex h-full flex-col p-6 sm:p-7">
      <div className="flex items-start justify-between gap-4">
        <span
          className={`grid h-12 w-12 place-items-center rounded-xl border ${capability.borderColor} bg-gradient-to-br ${capability.gradient}`}
        >
          <Icon aria-hidden="true" size={20} className={capability.iconColor} />
        </span>
        <span
          className={[
            "inline-flex min-h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-semibold",
            needsSetup
              ? "border-amber-500/30 bg-amber-500/10 text-amber-400"
              : "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
          ].join(" ")}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${needsSetup ? "bg-amber-500" : "bg-emerald-500"}`} />
          {capability.statusLabel}
        </span>
      </div>

      <p className="mt-7 font-mono text-xs font-semibold text-blue-400">
        0{index + 1}
      </p>
      <h3 className="mt-2 text-xl font-semibold tracking-[-0.025em]" style={{ color: "var(--foreground)" }}>
        {capability.title}
      </h3>
      <p className="mt-3 text-sm leading-6" style={{ color: "var(--foreground-subtle)" }}>
        {capability.description}
      </p>
      <p className="mt-auto pt-6 text-xs leading-5" style={{ borderTop: "1px solid var(--border)", color: "var(--foreground-subtle)" }}>
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
          className="absolute left-6 top-14 h-[calc(100%-2rem)] w-px lg:left-[calc(50%+2rem)] lg:top-7 lg:h-px lg:w-[calc(100%-4rem)]"
          style={{ background: "linear-gradient(to bottom, var(--border), transparent)" }}
        />
      ) : null}

      <span
        className={`relative z-10 grid h-12 w-12 place-items-center rounded-xl border ${step.border} ${step.bg} shadow-sm lg:mx-auto`}
      >
        <Icon aria-hidden="true" size={20} className={step.color} />
      </span>
      <div className="pb-10 lg:pb-0 lg:pt-6 lg:text-center">
        <p className={`font-mono text-xs font-bold ${step.color}`}>
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
    <div className="zo-dark-page min-h-dvh" style={{ background: "var(--background)", color: "var(--foreground)" }}>
      {/* Aurora background */}
      <div className="zo-aurora" aria-hidden="true" />

      <PublicHeader />

      <main id="main-content" className="relative z-10">
        {/* ═══ HERO ═══ */}
        <section className="relative overflow-hidden" style={{ borderBottom: "1px solid var(--border)" }}>
          <div className="zo-grid-overlay" aria-hidden="true" />

          <div className="relative mx-auto grid w-full max-w-7xl gap-12 px-4 py-16 sm:px-6 sm:py-24 lg:grid-cols-[1.05fr_.95fr] lg:items-center lg:gap-16 lg:px-8 lg:py-28">
            <div>
              <div
                className="inline-flex items-center gap-2.5 rounded-full px-3.5 py-1.5 text-xs font-semibold"
                style={{ border: "1px solid var(--border)", background: "var(--card)", color: "var(--primary)", boxShadow: "var(--shadow-glow-blue)" }}
              >
                <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse shadow-[0_0_6px_rgba(59,130,246,0.6)]" />
                Azure App Service · Deployment Platform
              </div>

              <h1 className="mt-8 max-w-3xl text-balance text-4xl font-bold leading-[1.08] tracking-[-0.03em] sm:text-5xl lg:text-6xl">
                <span style={{ color: "var(--foreground)" }}>See what will happen </span>
                <span className="bg-gradient-to-r from-blue-400 via-indigo-400 to-cyan-400 bg-clip-text text-transparent">
                  before a release
                </span>
                <span style={{ color: "var(--foreground)" }}> reaches Azure.</span>
              </h1>
              <p className="mt-6 max-w-2xl text-pretty text-base leading-7 sm:text-lg sm:leading-8" style={{ color: "var(--foreground-subtle)" }}>
                Create a commit-pinned release record, inspect every recorded
                validation outcome, and approve the exact plan. Missing tools,
                telemetry, or cloud prerequisites stay visibly unavailable.
              </p>

              <div className="mt-10 flex flex-col gap-3 sm:flex-row">
                <Link
                  href="/signup"
                  className="group inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-blue-600 px-6 text-sm font-semibold text-white shadow-lg shadow-blue-500/25 transition-all duration-200 hover:bg-blue-500 hover:shadow-blue-500/35 hover:shadow-xl active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[#06090f]"
                >
                  Get started free
                  <ArrowRight
                    aria-hidden="true"
                    size={16}
                    className="transition-transform duration-200 group-hover:translate-x-0.5"
                  />
                </Link>
                <a
                  href="#capabilities"
                  className="inline-flex min-h-12 items-center justify-center rounded-xl px-6 text-sm font-semibold transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 hover:border-[var(--border-hover)]"
                  style={{ border: "1px solid var(--border)", background: "var(--card)", color: "var(--foreground)" }}
                >
                  See capabilities
                </a>
              </div>

              <ul
                aria-label="Evidence principles"
                className="mt-8 flex flex-wrap gap-x-6 gap-y-3 text-sm"
                style={{ color: "var(--foreground-subtle)" }}
              >
                {proofPoints.map((item) => (
                  <li key={item} className="inline-flex items-center gap-2">
                    <Check
                      aria-hidden="true"
                      size={15}
                      strokeWidth={2.5}
                      className="text-emerald-400"
                    />
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            <HomeHeroMotion />
          </div>
        </section>

        {/* ═══ METRICS STRIP ═══ */}
        <section style={{ background: "var(--background-secondary)", borderBottom: "1px solid var(--border)" }}>
          <div className="mx-auto w-full max-w-5xl px-4 py-10 sm:px-6 lg:px-8">
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
              {metrics.map((m) => (
                <div key={m.label} className="text-center">
                  <p className="text-3xl font-bold tracking-tight bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
                    {m.value}
                  </p>
                  <p className="mt-1 text-sm font-semibold" style={{ color: "var(--foreground)" }}>{m.label}</p>
                  <p className="text-xs" style={{ color: "var(--foreground-subtle)" }}>{m.sublabel}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ═══ CAPABILITIES ═══ */}
        <section
          id="capabilities"
          className="scroll-mt-20"
          style={{ borderBottom: "1px solid var(--border)", background: "var(--background)" }}
        >
          <div className="mx-auto w-full max-w-7xl px-4 py-20 sm:px-6 sm:py-24 lg:px-8 lg:py-28">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
              <div className="max-w-3xl">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-blue-400">
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

            <div className="mt-12 grid gap-5 lg:grid-cols-3">
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

        {/* ═══ WORKFLOW ═══ */}
        <section id="workflow" className="scroll-mt-20" style={{ borderBottom: "1px solid var(--border)", background: "var(--background-secondary)" }}>
          <div className="mx-auto w-full max-w-6xl px-4 py-20 sm:px-6 sm:py-24 lg:px-8 lg:py-28">
            <div className="mx-auto max-w-3xl text-left sm:text-center">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-blue-400">
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
              aria-label="ZeroOps workflow"
              className="mt-14 grid gap-0 lg:grid-cols-3 lg:gap-10"
            >
              {workflow.map((step, index) => (
                <WorkflowStep key={step.number} step={step} index={index} />
              ))}
            </ol>
          </div>
        </section>

        {/* ═══ BOTTOM CTA ═══ */}
        <section style={{ background: "var(--background)" }}>
          <div className="mx-auto w-full max-w-7xl px-4 py-20 sm:px-6 sm:py-24 lg:px-8">
            <div
              className="zo-glow-card relative p-8 sm:p-12 lg:p-14"
            >
              <div
                aria-hidden="true"
                className="pointer-events-none absolute -right-20 -top-28 h-80 w-80 rounded-full blur-3xl"
                style={{ background: "rgba(59, 130, 246, 0.08)" }}
              />
              <div
                aria-hidden="true"
                className="pointer-events-none absolute -left-20 -bottom-28 h-80 w-80 rounded-full blur-3xl"
                style={{ background: "rgba(16, 185, 129, 0.06)" }}
              />

              <div className="relative grid gap-10 lg:grid-cols-[1fr_auto] lg:items-end lg:gap-14">
                <div className="max-w-3xl">
                  <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-emerald-400">
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

                  <div className="mt-8 flex flex-wrap gap-x-6 gap-y-2">
                    <Link
                      href="/docs"
                      className="inline-flex min-h-11 items-center gap-1 font-semibold text-blue-400 transition-colors duration-150 hover:text-blue-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    >
                      Read the documentation
                      <ArrowRight size={14} aria-hidden="true" />
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
                  className="group inline-flex min-h-12 shrink-0 items-center justify-center gap-2 rounded-xl bg-blue-600 px-6 text-sm font-semibold text-white shadow-lg shadow-blue-500/25 transition-all duration-200 hover:bg-blue-500 hover:shadow-blue-500/35 hover:shadow-xl active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[#06090f]"
                >
                  Get started free
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
