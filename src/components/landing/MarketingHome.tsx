"use client";

import Link from "next/link";
import { motion, type Variants, useReducedMotion } from "framer-motion";
import {
  Activity,
  ArrowRight,
  Check,
  FileSearch,
  GitBranch,
  KeyRound,
  Layers3,
  LockKeyhole,
  Radar,
  Rocket,
  ScrollText,
  ServerCog,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";

const deliverySteps = [
  {
    number: "01",
    title: "Create a workspace",
    description: "Start a workspace for the application you want to bring to production. It becomes the place where release decisions and operational context stay connected.",
    icon: Layers3,
  },
  {
    number: "02",
    title: "Bring in your source",
    description: "Connect a GitHub repository or upload a ZIP file. ZeroOps uses that recorded source as the starting point for the delivery workflow.",
    icon: GitBranch,
  },
  {
    number: "03",
    title: "Review the application analysis",
    description: "See the application evidence, proposed configuration, and infrastructure recommendation before any production action is available.",
    icon: FileSearch,
  },
  {
    number: "04",
    title: "Set the delivery context",
    description: "Choose the deployment target and configure the environment values the application needs. Keep secret values out of the source repository.",
    icon: ServerCog,
  },
  {
    number: "05",
    title: "Approve, then launch",
    description: "Confirm the infrastructure plan and start the deployment when it is right for your team. Automation prepares the work; you authorize the release.",
    icon: Rocket,
  },
  {
    number: "06",
    title: "Operate with context",
    description: "Follow deployment activity, logs, monitoring signals, security status, incidents, and scaling from the same application workspace.",
    icon: Activity,
  },
];

const controlPoints = [
  {
    title: "One connected workspace",
    description: "Applications, deployment activity, logs, monitoring, security, and settings stay close to the release they relate to.",
    icon: Layers3,
  },
  {
    title: "Review gates stay human",
    description: "A proposed infrastructure plan must be reviewed and approved before you can start the production deployment workflow.",
    icon: LockKeyhole,
  },
  {
    title: "Operational visibility follows the release",
    description: "After a deployment begins, use the workspace to follow recorded activity and investigate the running application.",
    icon: Radar,
  },
];

const policies = [
  {
    title: "Approval policy",
    description: "ZeroOps prepares an application and infrastructure plan from recorded source evidence. Production deployment is an explicit, user-initiated step after the plan is approved.",
    icon: ShieldCheck,
  },
  {
    title: "Access policy",
    description: "Sensitive product actions are protected by authentication and scoped to the project you own. Keep workspace access limited to the people responsible for the application.",
    icon: LockKeyhole,
  },
  {
    title: "Configuration & secret policy",
    description: "Add environment variables through workspace settings and mark sensitive values as secrets. Treat credentials as runtime configuration, not source-code content.",
    icon: KeyRound,
  },
  {
    title: "Responsible automation policy",
    description: "Automation helps analyze, recommend, and organize delivery work. It is designed to make the decision clear, not to hide the decision-maker.",
    icon: Workflow,
  },
];

const faqs = [
  {
    question: "What can I connect?",
    answer: "Start with a GitHub repository or a ZIP upload. That source is used to build the application record and support the analysis and planning workflow.",
  },
  {
    question: "What happens before a production deployment?",
    answer: "ZeroOps prepares an infrastructure plan from the recorded application analysis. You review and approve that plan, then explicitly start the deployment workflow when ready.",
  },
  {
    question: "Where should I add configuration and secrets?",
    answer: "Use workspace settings for environment variables and designate sensitive values as secrets. Avoid storing credentials directly in the repository or ZIP you connect.",
  },
  {
    question: "Where do I see what happened after launch?",
    answer: "The application workspace brings together deployment activity, logs, available monitoring data, security status, incidents, and scaling controls.",
  },
];

const signalItems = [
  "Source connected",
  "Architecture reviewed",
  "Approval stays human",
  "Live context stays close",
];

const reveal: Variants = {
  hidden: { opacity: 0, y: 18 },
  visible: (index: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: index * 0.09, duration: 0.5, ease: [0.22, 1, 0.36, 1] as const },
  }),
};

export function MarketingHome() {
  const shouldReduceMotion = useReducedMotion();

  return (
    <main id="main-content" className="relative min-h-screen overflow-hidden bg-background text-foreground selection:bg-primary/25">
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[780px] overflow-hidden">
        <div className="ops-hero-orb absolute left-[8%] top-[-280px] h-[620px] w-[620px] rounded-full bg-primary/18 blur-[145px]" />
        <div className="ops-hero-orb ops-hero-orb-delayed absolute right-[5%] top-[-250px] h-[560px] w-[560px] rounded-full bg-accent/16 blur-[150px]" />
        <div className="ops-page-grid absolute inset-0 opacity-60" />
      </div>

      <div className="ops-signal-tape relative z-20" aria-label="ZeroOps operating principles">
        <p className="sr-only">ZeroOps operating principles: source connected, architecture reviewed, approval stays human, and live context stays close.</p>
        <motion.div aria-hidden="true" className="ops-signal-track" animate={shouldReduceMotion ? { x: "0%" } : { x: ["0%", "-50%"] }} transition={shouldReduceMotion ? { duration: 0 } : { duration: 28, ease: "linear", repeat: Infinity }}>
          {[...signalItems, ...signalItems].map((item, index) => (
            <span key={`${item}-${index}`} className="ops-signal-item"><span className="h-1.5 w-1.5 rounded-full bg-accent" />{item}</span>
          ))}
        </motion.div>
      </div>

      <header className="relative z-10 mx-auto flex w-full max-w-7xl items-center justify-between px-5 py-5 sm:px-8">
        <Link href="/" aria-label="ZeroOps home" className="flex items-center gap-2.5 font-semibold tracking-tight">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-primary to-accent shadow-lg shadow-primary/20">
            <span className="h-3.5 w-3.5 rounded-[5px] border-2 border-white/90" />
          </span>
          <span className="text-lg">ZeroOps</span>
        </Link>
        <nav aria-label="Primary navigation" className="hidden items-center gap-5 text-sm text-foreground-muted md:flex">
          <a href="#how-it-works" className="transition-colors hover:text-foreground">How it works</a>
          <a href="#controls" className="transition-colors hover:text-foreground">Controls</a>
          <a href="#policies" className="transition-colors hover:text-foreground">Policies</a>
          <a href="#questions" className="transition-colors hover:text-foreground">Questions</a>
        </nav>
        <div className="flex items-center gap-1.5 sm:gap-3">
          <Link href="/login" className="rounded-lg px-3 py-2 text-sm font-medium text-foreground-muted transition hover:bg-card hover:text-foreground">Sign in</Link>
          <Link href="/signup" className="ops-hero-primary rounded-xl px-4 py-2.5 text-sm">Start building</Link>
        </div>
      </header>

      <section className="relative z-10 mx-auto flex max-w-7xl flex-col items-center px-5 pb-20 pt-16 text-center sm:px-8 sm:pt-20 lg:pb-28 lg:pt-24">
        <motion.div custom={0} variants={reveal} initial="hidden" animate="visible" className="mb-7 inline-flex items-center gap-2 rounded-full border border-border bg-card/70 px-3 py-1.5 text-xs font-medium text-foreground-muted shadow-sm backdrop-blur">
          <Sparkles size={13} className="text-accent" />
          A quieter control plane for application delivery
        </motion.div>
        <motion.h1 custom={1} variants={reveal} initial="hidden" animate="visible" className="max-w-6xl text-balance text-5xl font-semibold leading-[0.94] tracking-[-0.065em] sm:text-7xl lg:text-[5.9rem]">
          Ship your application. <span className="block">Keep the <em className="ops-hero-emphasis">control.</em></span>
        </motion.h1>
        <motion.p custom={2} variants={reveal} initial="hidden" animate="visible" className="mt-7 max-w-2xl text-pretty text-base leading-7 text-foreground-muted sm:text-lg">
          ZeroOps turns a repository or ZIP upload into a clear, reviewable path to production&mdash;then keeps the operational context within reach after launch.
        </motion.p>
        <motion.div custom={3} variants={reveal} initial="hidden" animate="visible" className="mt-9 flex w-full max-w-md flex-col gap-3 sm:max-w-none sm:flex-row sm:justify-center">
          <Link href="/signup" className="ops-hero-primary group inline-flex items-center justify-center gap-2 rounded-xl px-5 py-3.5 text-sm">
            Create your workspace <ArrowRight size={16} className="transition-transform group-hover:translate-x-0.5" />
          </Link>
          <a href="#how-it-works" className="ops-secondary inline-flex items-center justify-center rounded-xl px-5 py-3.5 text-sm">See how it works</a>
        </motion.div>
        <motion.ul custom={4} variants={reveal} initial="hidden" animate="visible" aria-label="ZeroOps workflow highlights" className="mt-7 flex flex-wrap justify-center gap-x-4 gap-y-2 text-xs text-foreground-muted">
          {["GitHub or ZIP input", "Architecture review", "Human approval", "Live operations"].map((item) => (
            <li key={item} className="inline-flex items-center gap-1.5"><Check size={14} className="text-success" />{item}</li>
          ))}
        </motion.ul>

        <motion.div custom={5} variants={reveal} initial="hidden" animate="visible" className="ops-hero-console mt-14 w-full max-w-5xl overflow-hidden rounded-3xl border border-border p-2 text-left sm:p-3">
          <div className="rounded-2xl border border-border bg-background-secondary/75 p-4 sm:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-5">
              <div className="flex items-center gap-3">
                <span className="status-dot status-dot-blue" />
                <div><p className="text-sm font-semibold">Release workspace</p><p className="mt-0.5 text-xs text-foreground-muted">A connected path from source evidence to live operations</p></div>
              </div>
              <span className="rounded-full border border-border bg-card px-2.5 py-1 text-[11px] font-medium text-foreground-muted">Ready for review</span>
            </div>
            <div className="grid gap-4 py-5 lg:grid-cols-[1.2fr_.8fr]">
              <div className="ops-card rounded-2xl p-4 sm:p-5">
                <div className="flex items-center justify-between gap-4"><p className="text-xs font-medium text-foreground-muted">The delivery path</p><span className="text-[11px] font-medium text-primary">Decision points stay visible</span></div>
                <div className="mt-5 space-y-3">
                  {[
                    ["Source connected", "Repository or ZIP becomes the starting point"],
                    ["Infrastructure plan prepared", "Review the proposed setup and configuration"],
                    ["Release authorized", "Start deployment when you approve the plan"],
                  ].map(([title, detail], index) => (
                    <div key={title} className="flex gap-3 rounded-xl border border-border/80 bg-background/45 p-3">
                      <span className="grid h-7 w-7 flex-none place-items-center rounded-lg bg-primary-subtle text-xs font-bold text-primary">{index + 1}</span>
                      <div><p className="text-sm font-semibold">{title}</p><p className="mt-0.5 text-xs text-foreground-muted">{detail}</p></div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="ops-card rounded-2xl p-4 sm:p-5">
                <p className="text-xs font-medium text-foreground-muted">What stays connected</p>
                <div className="mt-4 space-y-3">
                  {["Application analysis", "Approval and deployment activity", "Logs, monitoring, and security status"].map((item) => (
                    <div key={item} className="flex items-center gap-2.5 text-sm text-foreground"><span className="grid h-5 w-5 place-items-center rounded-full bg-success-subtle"><Check size={12} className="text-success" /></span>{item}</div>
                  ))}
                </div>
                <a href="#policies" className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-primary transition hover:text-primary-hover">Read the operating policies <ArrowRight size={15} /></a>
              </div>
            </div>
          </div>
        </motion.div>
      </section>

      <section id="how-it-works" className="relative z-10 border-y border-border bg-card/35 px-5 py-20 sm:px-8">
        <div className="mx-auto max-w-7xl">
          <motion.div initial={{ opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.35 }} className="max-w-2xl">
            <p className="ops-kicker">How ZeroOps works</p>
            <h2 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">A clear path from your code to an operating application.</h2>
            <p className="mt-4 text-base leading-7 text-foreground-muted">The workflow is deliberately ordered so you understand what the application needs before you make a production decision.</p>
          </motion.div>
          <ol className="mt-10 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {deliverySteps.map((step, index) => {
              const Icon = step.icon;
              return <motion.li key={step.number} initial={{ opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.2 }} transition={{ delay: index * 0.06, duration: 0.42 }} className="ops-card-interactive rounded-2xl p-6">
                <div className="flex items-center justify-between"><span className="font-mono text-xs text-foreground-muted">{step.number}</span><span className="grid h-10 w-10 place-items-center rounded-xl bg-primary-subtle text-primary"><Icon size={19} /></span></div>
                <h3 className="mt-9 text-lg font-semibold">{step.title}</h3><p className="mt-2 text-sm leading-6 text-foreground-muted">{step.description}</p>
              </motion.li>;
            })}
          </ol>
        </div>
      </section>

      <section id="controls" className="relative z-10 mx-auto max-w-7xl px-5 py-24 sm:px-8">
        <div className="grid gap-10 lg:grid-cols-[.88fr_1.12fr] lg:items-end">
          <div><p className="ops-kicker">Your work, still your call</p><h2 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">Automation should remove noise, not remove your control.</h2><p className="mt-4 max-w-xl text-base leading-7 text-foreground-muted">ZeroOps gives each stage a home: source, plan, launch, and the operating work that follows. You can move through those stages without losing the details behind the decision.</p><Link href="/signup" className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-primary transition hover:text-primary-hover">Explore the workspace <ArrowRight size={16} /></Link></div>
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            {controlPoints.map((point) => { const Icon = point.icon; return <article key={point.title} className="ops-card flex gap-4 rounded-2xl p-5"><span className="grid h-10 w-10 flex-none place-items-center rounded-xl bg-accent-subtle text-accent"><Icon size={19} /></span><div><h3 className="text-sm font-semibold">{point.title}</h3><p className="mt-1.5 text-sm leading-6 text-foreground-muted">{point.description}</p></div></article>; })}
          </div>
        </div>
      </section>

      <section id="policies" className="relative z-10 border-y border-border bg-card/35 px-5 py-20 sm:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="grid gap-10 lg:grid-cols-[.72fr_1.28fr]">
            <div>
              <p className="ops-kicker"><ScrollText size={13} /> Operating policies</p>
              <h2 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">Clear boundaries for every delivery decision.</h2>
              <p className="mt-4 max-w-xl text-base leading-7 text-foreground-muted">These policies explain how the product is intended to be used in a production-style workflow. They make the control points explicit for everyone using the workspace.</p>
              <p className="mt-5 max-w-xl text-sm leading-6 text-foreground-muted">This is a product operating overview, not a substitute for formal legal terms or a negotiated data-processing agreement.</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {policies.map((policy) => {
                const Icon = policy.icon;
                return <article key={policy.title} className="ops-card rounded-2xl p-5">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-primary-subtle text-primary"><Icon size={18} /></span>
                  <h3 className="mt-5 text-base font-semibold">{policy.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-foreground-muted">{policy.description}</p>
                </article>;
              })}
            </div>
          </div>
        </div>
      </section>

      <section id="questions" className="relative z-10 mx-auto max-w-7xl px-5 py-24 sm:px-8">
        <div className="grid gap-10 lg:grid-cols-[.7fr_1.3fr]">
          <div><p className="ops-kicker">Questions, answered</p><h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">Start with clarity.</h2><p className="mt-4 text-base leading-7 text-foreground-muted">Set up your workspace when you are ready. Existing teams can sign in and pick up where they left off.</p></div>
          <div className="space-y-3">{faqs.map((faq) => <details key={faq.question} className="ops-card group rounded-2xl px-5 py-4"><summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-semibold marker:content-none"><span>{faq.question}</span><span aria-hidden="true" className="text-lg text-primary transition-transform group-open:rotate-45">+</span></summary><p className="pt-3 text-sm leading-6 text-foreground-muted">{faq.answer}</p></details>)}</div>
        </div>
      </section>

      <section className="relative z-10 mx-auto max-w-7xl px-5 pb-20 sm:px-8 sm:pb-24">
        <div className="overflow-hidden rounded-3xl border border-primary/25 bg-gradient-to-br from-primary-subtle via-card to-accent-subtle p-8 text-center sm:p-12">
          <p className="ops-kicker">Ready when you are</p><h2 className="mx-auto mt-3 max-w-2xl text-balance text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">Bring your application into a workspace built for the full delivery journey.</h2><p className="mx-auto mt-4 max-w-xl text-sm leading-6 text-foreground-muted">Start from your source, review the plan, launch on your terms, and keep operational context close after release.</p><div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row"><Link href="/signup" className="ops-primary inline-flex items-center justify-center gap-2 rounded-xl px-5 py-3.5 text-sm">Create your workspace <ArrowRight size={16} /></Link><Link href="/login" className="ops-secondary inline-flex items-center justify-center rounded-xl px-5 py-3.5 text-sm">Sign in</Link></div>
        </div>
      </section>

      <footer className="relative z-10 mx-auto flex max-w-7xl flex-col gap-4 border-t border-border px-5 py-8 text-xs text-foreground-muted sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <p>&copy; {new Date().getFullYear()} ZeroOps</p>
        <nav aria-label="Footer navigation" className="flex flex-wrap gap-x-4 gap-y-2"><a href="#how-it-works" className="transition hover:text-foreground">How it works</a><a href="#policies" className="transition hover:text-foreground">Operating policies</a><a href="#questions" className="transition hover:text-foreground">FAQ</a></nav>
      </footer>
    </main>
  );
}
