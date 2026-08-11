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
      className="relative overflow-hidden rounded-3xl border border-border bg-card p-2 shadow-[var(--shadow-md)]"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-primary-glow blur-3xl"
      />

      <div className="relative rounded-[1.15rem] border border-border bg-background-secondary/90">
        <div className="flex flex-col gap-3 border-b border-border px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-sm font-semibold">Illustrative release review</p>
            <p className="mt-1 text-xs leading-5 text-foreground-muted">
              Example only. Dashboard states come from recorded events.
            </p>
          </div>
          <span className="inline-flex min-h-7 w-fit items-center gap-1.5 rounded-full border border-warning/25 bg-warning-subtle px-2.5 text-xs font-semibold text-warning-hover">
            <LockKeyhole aria-hidden="true" size={13} />
            Approval required
          </span>
        </div>

        <ol aria-label="Illustrative release path" className="p-4 sm:p-5">
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
                className="relative grid grid-cols-[2.5rem_minmax(0,1fr)] gap-3 pb-3 last:pb-0"
              >
                {index < illustratedFlow.length - 1 ? (
                  <span
                    aria-hidden="true"
                    className="absolute left-[1.22rem] top-10 h-[calc(100%-0.5rem)] w-px bg-border"
                  />
                ) : null}

                <span className="relative z-10 grid h-10 w-10 place-items-center rounded-xl border border-primary/20 bg-card text-primary shadow-sm">
                  <Icon aria-hidden="true" size={17} />
                </span>

                <div className="flex min-w-0 flex-col gap-2 rounded-xl border border-border bg-card/95 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-foreground">
                      {item.label}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-foreground-muted">
                      {item.detail}
                    </p>
                  </div>
                  <span
                    className={[
                      "inline-flex min-h-7 w-fit shrink-0 items-center rounded-full border px-2.5 text-xs font-semibold",
                      item.tone === "warning"
                        ? "border-warning/25 bg-warning-subtle text-warning-hover"
                        : "border-primary/20 bg-primary-subtle text-primary-hover",
                    ].join(" ")}
                  >
                    {item.state}
                  </span>
                </div>
              </motion.li>
            );
          })}
        </ol>

        <div className="border-t border-border px-5 py-4">
          <p className="flex gap-2 text-xs leading-5 text-foreground-muted">
            <Check
              aria-hidden="true"
              size={14}
              strokeWidth={2.5}
              className="mt-0.5 shrink-0 text-success"
            />
            If a required tool cannot report, its gate stays unavailable. No
            completion or live cloud activity is implied here.
          </p>
        </div>
      </div>
    </motion.div>
  );
}
