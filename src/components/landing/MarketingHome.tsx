"use client";

import Link from "next/link";
import { motion, type Variants } from "framer-motion";
import { ArrowRight, Check, Code2, GitBranch, ShieldCheck, Sparkles } from "lucide-react";

const journey = [
  { number: "01", title: "Bring your code", description: "Connect a GitHub repository or upload a ZIP file.", icon: GitBranch },
  { number: "02", title: "Review what matters", description: "See the app basics, required configuration, and any decisions that need you.", icon: Code2 },
  { number: "03", title: "Go live with confidence", description: "Approve the launch, then follow one calm, clear status view.", icon: ShieldCheck },
];

const reveal: Variants = {
  hidden: { opacity: 0, y: 18 },
  visible: (index: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: index * 0.1, duration: 0.55, ease: [0.22, 1, 0.36, 1] as const },
  }),
};

export function MarketingHome() {
  return (
    <main className="min-h-screen overflow-hidden bg-[#0a0b10] text-white selection:bg-violet-400/30">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[720px] overflow-hidden">
        <div className="absolute left-[12%] top-[-300px] h-[620px] w-[620px] rounded-full bg-blue-500/20 blur-[150px]" />
        <div className="absolute right-[4%] top-[-250px] h-[520px] w-[520px] rounded-full bg-violet-500/20 blur-[150px]" />
        <div className="absolute inset-0 opacity-[0.045] [background-image:linear-gradient(rgba(255,255,255,.8)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.8)_1px,transparent_1px)] [background-size:44px_44px]" />
      </div>

      <header className="relative z-10 mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-5 sm:px-8">
        <Link href="/" className="flex items-center gap-2.5 font-semibold tracking-tight">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-blue-500 to-violet-500 shadow-lg shadow-blue-500/20">
            <span className="h-3.5 w-3.5 rounded-[5px] border-2 border-white/90" />
          </span>
          <span>ZeroOps</span>
        </Link>
        <div className="flex items-center gap-2 sm:gap-4">
          <Link href="/login" className="px-3 py-2 text-sm text-white/70 transition hover:text-white">Sign in</Link>
          <Link href="/signup" className="rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-zinc-950 transition hover:-translate-y-0.5 hover:bg-white/90">Get started</Link>
        </div>
      </header>

      <section className="relative z-10 mx-auto flex max-w-6xl flex-col items-center px-5 pb-24 pt-20 text-center sm:px-8 sm:pt-28 lg:pb-32">
        <motion.div custom={0} variants={reveal} initial="hidden" animate="visible" className="mb-7 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.055] px-3 py-1.5 text-xs font-medium text-white/70 shadow-sm backdrop-blur">
          <Sparkles size={13} className="text-violet-300" />
          Your application, without the platform overhead
        </motion.div>
        <motion.h1 custom={1} variants={reveal} initial="hidden" animate="visible" className="max-w-4xl text-balance text-5xl font-semibold leading-[1.03] tracking-[-0.055em] sm:text-6xl lg:text-7xl">
          From code to live—<span className="bg-gradient-to-r from-blue-300 via-violet-300 to-fuchsia-300 bg-clip-text text-transparent"> without a cloud console.</span>
        </motion.h1>
        <motion.p custom={2} variants={reveal} initial="hidden" animate="visible" className="mt-7 max-w-2xl text-pretty text-base leading-7 text-white/60 sm:text-lg">
          ZeroOps prepares, launches, and looks after your application. You stay focused on the choices that matter: your code, your controls, and when to go live.
        </motion.p>
        <motion.div custom={3} variants={reveal} initial="hidden" animate="visible" className="mt-9 flex flex-col gap-3 sm:flex-row">
          <Link href="/signup" className="group inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-500 to-violet-500 px-5 py-3.5 text-sm font-semibold shadow-lg shadow-violet-500/25 transition hover:-translate-y-0.5 hover:shadow-violet-500/40">
            Connect your code <ArrowRight size={16} className="transition-transform group-hover:translate-x-0.5" />
          </Link>
          <Link href="/login" className="inline-flex items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] px-5 py-3.5 text-sm font-semibold text-white/85 transition hover:border-white/20 hover:bg-white/[0.08]">Open workspace</Link>
        </motion.div>

        <motion.div custom={4} variants={reveal} initial="hidden" animate="visible" className="mt-16 w-full max-w-4xl overflow-hidden rounded-2xl border border-white/10 bg-[#10121a]/90 p-2 text-left shadow-2xl shadow-black/40 backdrop-blur sm:p-3">
          <div className="rounded-xl border border-white/[0.07] bg-[#0c0d13] p-5 sm:p-7">
            <div className="flex items-center justify-between border-b border-white/[0.07] pb-5">
              <div className="flex items-center gap-3"><span className="h-2.5 w-2.5 rounded-full bg-emerald-400 shadow-[0_0_14px_rgba(74,222,128,.6)]" /><div><p className="text-sm font-semibold">Ready when you are</p><p className="mt-0.5 text-xs text-white/45">One place for every application</p></div></div>
              <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-[11px] font-medium text-white/60">Workspace</span>
            </div>
            <div className="grid gap-4 py-5 sm:grid-cols-[1.3fr_.7fr]">
              <div className="rounded-xl border border-white/[0.07] bg-white/[0.025] p-4"><p className="text-xs font-medium text-white/50">Next step</p><p className="mt-2 text-lg font-semibold">Add your first application</p><p className="mt-1 text-sm leading-6 text-white/50">Choose GitHub or upload a ZIP. We&apos;ll take care of the setup behind the scenes.</p><div className="mt-4 h-2 overflow-hidden rounded-full bg-white/[0.06]"><motion.div className="h-full rounded-full bg-gradient-to-r from-blue-400 to-violet-400" initial={{ width: "18%" }} animate={{ width: ["18%", "62%", "44%", "18%"] }} transition={{ duration: 7, repeat: Infinity, ease: "easeInOut" }} /></div></div>
              <div className="rounded-xl border border-white/[0.07] bg-white/[0.025] p-4"><p className="text-xs font-medium text-white/50">You stay in control</p><div className="mt-3 space-y-3">{["Review before launch", "Clear live status", "Manage paid actions"].map((item) => <div key={item} className="flex items-center gap-2 text-sm text-white/75"><span className="grid h-5 w-5 place-items-center rounded-full bg-emerald-400/10"><Check size={12} className="text-emerald-300" /></span>{item}</div>)}</div></div>
            </div>
          </div>
        </motion.div>
      </section>

      <section className="relative z-10 border-y border-white/[0.07] bg-white/[0.025] px-5 py-20 sm:px-8">
        <div className="mx-auto max-w-6xl"><motion.div initial={{ opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.35 }} className="max-w-xl"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-violet-300">A simpler way to ship</p><h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">A quiet workflow for serious products.</h2></motion.div><div className="mt-10 grid gap-4 md:grid-cols-3">{journey.map((step, index) => { const Icon = step.icon; return <motion.article key={step.number} initial={{ opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.2 }} transition={{ delay: index * 0.1, duration: 0.45 }} className="rounded-2xl border border-white/[0.08] bg-[#10121a]/70 p-6 transition hover:-translate-y-1 hover:border-white/[0.15]"><div className="flex items-center justify-between"><span className="text-xs font-mono text-white/35">{step.number}</span><span className="grid h-10 w-10 place-items-center rounded-xl bg-white/[0.06] text-violet-200"><Icon size={19} /></span></div><h3 className="mt-9 text-lg font-semibold">{step.title}</h3><p className="mt-2 text-sm leading-6 text-white/55">{step.description}</p></motion.article>; })}</div></div>
      </section>

      <footer className="relative z-10 mx-auto flex max-w-6xl flex-col gap-4 px-5 py-8 text-xs text-white/40 sm:flex-row sm:items-center sm:justify-between sm:px-8"><p>© {new Date().getFullYear()} ZeroOps</p><p>Built to keep complex work out of your way.</p></footer>
    </main>
  );
}
