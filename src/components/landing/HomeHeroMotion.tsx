"use client";

import { motion, useReducedMotion } from "framer-motion";
import {
  Check,
  FileSearch,
  ListChecks,
  LockKeyhole,
  type LucideIcon,
} from "lucide-react";

const illustratedFlow = [
  {
    label: "Source selected",
    detail: "Revision and repository evidence recorded",
    state: "Recorded",
    icon: FileSearch,
    tone: "default",
  },
  {
    label: "Checks disclosed",
    detail: "Pass, fail, skip, block, or unavailable",
    state: "Policy gate",
    icon: ListChecks,
    tone: "default",
  },
  {
    label: "Exact approval",
    detail: "Unlocks a configured App Service job",
    state: "Setup needed",
    icon: LockKeyhole,
    tone: "warning",
  },
] as const satisfies ReadonlyArray<{
  label: string;
  detail: string;
  state: string;
  icon: LucideIcon;
  tone: "default" | "warning";
}>;

const easeOut = [0.22, 1, 0.36, 1] as const;

export function HomeHeroMotion() {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0.92, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: reduceMotion ? 0 : 0.2,
        ease: easeOut,
      }}
      className="relative overflow-hidden rounded-2xl p-2.5"
      style={{ border: "1px solid var(--border)", background: "var(--card)", boxShadow: "var(--shadow-lg)" }}
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-blue-600/10 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -left-20 -bottom-24 h-64 w-64 rounded-full bg-emerald-500/10 blur-3xl"
      />

      <div className="relative rounded-xl" style={{ border: "1px solid var(--border)", background: "var(--background-secondary)" }}>
        <div
          className="flex flex-col gap-3 border-b px-5 py-4 sm:flex-row sm:items-start sm:justify-between"
          style={{ borderBottom: "1px solid var(--border)", background: "var(--card)" }}
        >
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse shadow-[0_0_8px_rgba(59,130,246,0.6)]" />
              <p className="text-sm font-semibold" style={{ color: "var(--foreground)" }}>Release review pipeline</p>
            </div>
            <p className="mt-1 text-xs leading-5" style={{ color: "var(--foreground-subtle)" }}>
              Pipeline stages reflect real recorded events from your repository and deployment.
            </p>
          </div>
          <span className="inline-flex min-h-7 w-fit items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 text-xs font-semibold text-amber-400 shadow-[0_0_12px_rgba(245,158,11,0.15)]">
            <LockKeyhole aria-hidden="true" size={13} />
            Approval required
          </span>
        </div>

        <ol aria-label="Release review pipeline" className="p-4 sm:p-5 space-y-3">
          {illustratedFlow.map((item, index) => {
            const Icon = item.icon;

            return (
              <motion.li
                key={item.label}
                initial={reduceMotion ? false : { opacity: 0.82, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  delay: reduceMotion ? 0 : index * 0.04,
                  duration: reduceMotion ? 0 : 0.2,
                  ease: easeOut,
                }}
                className="relative grid grid-cols-[2.5rem_minmax(0,1fr)] gap-3 pb-1 last:pb-0"
              >
                {index < illustratedFlow.length - 1 ? (
                  <span
                    aria-hidden="true"
                    className="absolute left-[1.22rem] top-10 h-[calc(100%-0.5rem)] w-px"
                  style={{ background: "var(--border)" }}
                  />
                ) : null}

                <span
                  className="relative z-10 grid h-10 w-10 place-items-center rounded-xl shadow-sm"
                  style={{ border: "1px solid var(--primary-subtle)", background: "var(--surface-subtle)", color: "var(--primary)" }}
                >
                  <Icon aria-hidden="true" size={17} />
                </span>

                <div
                  className="flex min-w-0 flex-col gap-2 rounded-xl px-4 py-3 sm:flex-row sm:items-center sm:justify-between transition"
                  style={{ border: "1px solid var(--border)", background: "var(--card)" }}
                >
                  <div className="min-w-0">
                    <p className="text-xs font-semibold" style={{ color: "var(--foreground)" }}>
                      {item.label}
                    </p>
                    <p className="mt-0.5 text-xs leading-5" style={{ color: "var(--foreground-subtle)" }}>
                      {item.detail}
                    </p>
                  </div>
                  <span
                    className={[
                      "inline-flex min-h-7 w-fit shrink-0 items-center rounded-full border px-2.5 text-xs font-semibold",
                      item.tone === "warning"
                        ? "border-amber-500/30 bg-amber-500/10 text-amber-400"
                        : "border-blue-500/30 bg-blue-500/10 text-blue-400",
                    ].join(" ")}
                  >
                    {item.state}
                  </span>
                </div>
              </motion.li>
            );
          })}
        </ol>

        <div
          className="border-t px-5 py-3.5"
          style={{ borderTop: "1px solid var(--border)", background: "var(--background-secondary)" }}
        >
          <p className="flex gap-2 text-xs leading-5" style={{ color: "var(--foreground-subtle)" }}>
            <Check
              aria-hidden="true"
              size={14}
              strokeWidth={2.5}
              className="mt-0.5 shrink-0 text-emerald-400"
            />
            If a required tool cannot report, its gate stays unavailable. No
            completion or live cloud activity is implied here.
          </p>
        </div>
      </div>
    </motion.div>
  );
}
