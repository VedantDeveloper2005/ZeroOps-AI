"use client";

import Link from "next/link";
import { motion, type Variants } from "framer-motion";
import {
  ArrowRight,
  Check,
  Code2,
  GitBranch,
  Layers3,
  LockKeyhole,
  Radar,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

const journey = [
  {
    number: "01",
    title: "Bring your code",
    description: "Connect a GitHub repository or upload a ZIP file from one calm starting point.",
    icon: GitBranch,
  },
  {
    number: "02",
    title: "Review the plan",
    description: "Inspect the application, required configuration, and the decisions that need your approval.",
    icon: Code2,
  },
  {
    number: "03",
    title: "Launch with context",
    description: "Approve the release and follow deployment, observability, and security from your workspace.",
    icon: ShieldCheck,
  },
];

const controlPoints = [
  { title: "One connected workspace", description: "Applications, deployments, logs, and settings stay in the same product surface.", icon: Layers3 },
  { title: "Review gates stay human", description: "ZeroOps prepares the work, while you keep the final say before launch.", icon: LockKeyhole },
  { title: "Operational visibility", description: "Move from a deployment to monitoring, incident response, and security without losing context.", icon: Radar },
];

const faqs = [
  { question: "What can I connect?", answer: "You can begin with a GitHub repository or a ZIP upload, then continue inside the ZeroOps workspace." },
  { question: "Do I lose control of a release?", answer: "No. ZeroOps is designed to prepare and present the work clearly, with review steps before launch." },
  { question: "Where do I see what happened?", answer: "Your workspace brings deployment activity, monitoring, logs, security, and account controls together by application." },
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
  return (
    <main id="main-content" className="relative min-h-screen overflow-hidden bg-background text-foreground selection:bg-primary/25">
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[780px] overflow-hidden">
        <div className="absolute left-[8%] top-[-280px] h-[620px] w-[620px] rounded-full bg-primary/18 blur-[145px]" />
        <div className="absolute right-[5%] top-[-250px] h-[560px] w-[560px] rounded-full bg-accent/16 blur-[150px]" />
        <div className="ops-page-grid absolute inset-0 opacity-60" />
      </div>

      <header className="relative z-10 mx-auto flex w-full max-w-7xl items-center justify-between px-5 py-5 sm:px-8">
        <Link href="/" aria-label="ZeroOps home" className="flex items-center gap-2.5 font-semibold tracking-tight">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-primary to-accent shadow-lg shadow-primary/20">
            <span className="h-3.5 w-3.5 rounded-[5px] border-2 border-white/90" />
          </span>
          <span className="text-lg">ZeroOps</span>
        </Link>
        <nav aria-label="Primary navigation" className="hidden items-center gap-5 text-sm text-foreground-muted md:flex">
          <a href="#workflow" className="transition-colors hover:text-foreground">Workflow</a>
          <a href="#controls" className="transition-colors hover:text-foreground">Controls</a>
          <a href="#questions" className="transition-colors hover:text-foreground">Questions</a>
        </nav>
        <div className="flex items-center gap-1.5 sm:gap-3">
          <Link href="/login" className="rounded-lg px-3 py-2 text-sm font-medium text-foreground-muted transition hover:bg-card hover:text-foreground">Sign in</Link>
          <Link href="/signup" className="ops-primary rounded-xl px-4 py-2.5 text-sm">Start building</Link>
        </div>
      </header>

      <section className="relative z-10 mx-auto flex max-w-7xl flex-col items-center px-5 pb-24 pt-18 text-center sm:px-8 sm:pt-24 lg:pb-32 lg:pt-28">
        <motion.div custom={0} variants={reveal} initial="hidden" animate="visible" className="mb-7 inline-flex items-center gap-2 rounded-full border border-border bg-card/70 px-3 py-1.5 text-xs font-medium text-foreground-muted shadow-sm backdrop-blur">
          <Sparkles size={13} className="text-accent" />
          A quieter control plane for application delivery
        </motion.div>
        <motion.h1 custom={1} variants={reveal} initial="hidden" animate="visible" className="max-w-5xl text-balance text-5xl font-semibold leading-[1.02] tracking-[-0.055em] sm:text-6xl lg:text-7xl">
          Ship your application without carrying <span className="gradient-text">the platform overhead.</span>
        </motion.h1>
        <motion.p custom={2} variants={reveal} initial="hidden" animate="visible" className="mt-7 max-w-2xl text-pretty text-base leading-7 text-foreground-muted sm:text-lg">
          ZeroOps turns a repository or ZIP upload into a clear, reviewable delivery flow—so you can focus on your code, your controls, and the decision to go live.
        </motion.p>
        <motion.div custom={3} variants={reveal} initial="hidden" animate="visible" className="mt-9 flex w-full max-w-md flex-col gap-3 sm:max-w-none sm:flex-row sm:justify-center">
          <Link href="/signup" className="ops-primary group inline-flex items-center justify-center gap-2 rounded-xl px-5 py-3.5 text-sm">
            Create your workspace <ArrowRight size={16} className="transition-transform group-hover:translate-x-0.5" />
          </Link>
          <Link href="/login" className="ops-secondary inline-flex items-center justify-center rounded-xl px-5 py-3.5 text-sm">Open an existing workspace</Link>
        </motion.div>

        <motion.div custom={4} variants={reveal} initial="hidden" animate="visible" className="mt-16 w-full max-w-5xl overflow-hidden rounded-3xl border border-border bg-card/90 p-2 text-left shadow-2xl shadow-black/20 backdrop-blur sm:p-3">
          <div className="rounded-2xl border border-border bg-background-secondary/75 p-4 sm:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-5">
              <div className="flex items-center gap-3">
                <span className="status-dot status-dot-blue" />
                <div><p className="text-sm font-semibold">Release workspace</p><p className="mt-0.5 text-xs text-foreground-muted">A connected path from code to live operations</p></div>
              </div>
              <span className="rounded-full border border-border bg-card px-2.5 py-1 text-[11px] font-medium text-foreground-muted">Review in progress</span>
            </div>
            <div className="grid gap-4 py-5 lg:grid-cols-[1.2fr_.8fr]">
              <div className="ops-card rounded-2xl p-4 sm:p-5">
                <div className="flex items-center justify-between gap-4"><p className="text-xs font-medium text-foreground-muted">Delivery path</p><span className="text-[11px] font-medium text-primary">Your decision required</span></div>
                <div className="mt-5 space-y-3">
                  {[
                    ["Repository connected", "Source is ready for review"],
                    ["Application plan prepared", "Confirm configuration before launch"],
                    ["Release approval", "Choose when the deployment proceeds"],
                  ].map(([title, detail], index) => (
                    <div key={title} className="flex gap-3 rounded-xl border border-border/80 bg-background/45 p-3">
                      <span className="grid h-7 w-7 flex-none place-items-center rounded-lg bg-primary-subtle text-xs font-bold text-primary">{index + 1}</span>
                      <div><p className="text-sm font-semibold">{title}</p><p className="mt-0.5 text-xs text-foreground-muted">{detail}</p></div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="ops-card rounded-2xl p-4 sm:p-5">
                <p className="text-xs font-medium text-foreground-muted">Keep control at each step</p>
                <div className="mt-4 space-y-3">
                  {["Review before launch", "Trace deployment activity", "Move into live operations"].map((item) => (
                    <div key={item} className="flex items-center gap-2.5 text-sm text-foreground"><span className="grid h-5 w-5 place-items-center rounded-full bg-success-subtle"><Check size={12} className="text-success" /></span>{item}</div>
                  ))}
                </div>
                <Link href="/signup" className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-primary transition hover:text-primary-hover">Start with your code <ArrowRight size={15} /></Link>
              </div>
            </div>
          </div>
        </motion.div>
      </section>

      <section id="workflow" className="relative z-10 border-y border-border bg-card/35 px-5 py-20 sm:px-8">
        <div className="mx-auto max-w-7xl">
          <motion.div initial={{ opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.35 }} className="max-w-2xl">
            <p className="ops-kicker">A deliberate delivery flow</p>
            <h2 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">From source to operations, without losing the thread.</h2>
            <p className="mt-4 text-base leading-7 text-foreground-muted">Every step keeps the operational context close to the release that created it.</p>
          </motion.div>
          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {journey.map((step, index) => {
              const Icon = step.icon;
              return <motion.article key={step.number} initial={{ opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.2 }} transition={{ delay: index * 0.08, duration: 0.42 }} className="ops-card-interactive rounded-2xl p-6">
                <div className="flex items-center justify-between"><span className="font-mono text-xs text-foreground-muted">{step.number}</span><span className="grid h-10 w-10 place-items-center rounded-xl bg-primary-subtle text-primary"><Icon size={19} /></span></div>
                <h3 className="mt-9 text-lg font-semibold">{step.title}</h3><p className="mt-2 text-sm leading-6 text-foreground-muted">{step.description}</p>
              </motion.article>;
            })}
          </div>
        </div>
      </section>

      <section id="controls" className="relative z-10 mx-auto max-w-7xl px-5 py-24 sm:px-8">
        <div className="grid gap-10 lg:grid-cols-[.88fr_1.12fr] lg:items-end">
          <div><p className="ops-kicker">Your work, still your call</p><h2 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">Automation should remove noise, not remove your control.</h2><p className="mt-4 max-w-xl text-base leading-7 text-foreground-muted">ZeroOps gives each stage a home: setup, launch, and the operational work that follows.</p><Link href="/signup" className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-primary transition hover:text-primary-hover">Explore the workspace <ArrowRight size={16} /></Link></div>
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            {controlPoints.map((point) => { const Icon = point.icon; return <article key={point.title} className="ops-card flex gap-4 rounded-2xl p-5"><span className="grid h-10 w-10 flex-none place-items-center rounded-xl bg-accent-subtle text-accent"><Icon size={19} /></span><div><h3 className="text-sm font-semibold">{point.title}</h3><p className="mt-1.5 text-sm leading-6 text-foreground-muted">{point.description}</p></div></article>; })}
          </div>
        </div>
      </section>

      <section id="questions" className="relative z-10 border-t border-border bg-card/35 px-5 py-20 sm:px-8">
        <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[.7fr_1.3fr]">
          <div><p className="ops-kicker">Questions, answered</p><h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">Start with clarity.</h2><p className="mt-4 text-base leading-7 text-foreground-muted">Set up your workspace when you are ready. Existing teams can sign in and pick up where they left off.</p></div>
          <div className="space-y-3">{faqs.map((faq) => <details key={faq.question} className="ops-card group rounded-2xl px-5 py-4"><summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-semibold marker:content-none"><span>{faq.question}</span><span className="text-lg text-primary transition-transform group-open:rotate-45">+</span></summary><p className="pt-3 text-sm leading-6 text-foreground-muted">{faq.answer}</p></details>)}</div>
        </div>
      </section>

      <section className="relative z-10 mx-auto max-w-7xl px-5 py-20 sm:px-8">
        <div className="overflow-hidden rounded-3xl border border-primary/25 bg-gradient-to-br from-primary-subtle via-card to-accent-subtle p-8 text-center sm:p-12">
          <p className="ops-kicker">Ready when you are</p><h2 className="mx-auto mt-3 max-w-2xl text-balance text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">Bring your application into a workspace built for the whole delivery journey.</h2><div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row"><Link href="/signup" className="ops-primary inline-flex items-center justify-center gap-2 rounded-xl px-5 py-3.5 text-sm">Create your workspace <ArrowRight size={16} /></Link><Link href="/login" className="ops-secondary inline-flex items-center justify-center rounded-xl px-5 py-3.5 text-sm">Sign in</Link></div>
        </div>
      </section>

      <footer className="relative z-10 mx-auto flex max-w-7xl flex-col gap-3 border-t border-border px-5 py-8 text-xs text-foreground-muted sm:flex-row sm:items-center sm:justify-between sm:px-8"><p>© {new Date().getFullYear()} ZeroOps</p><p>Application delivery with a calmer operating model.</p></footer>
    </main>
  );
}
