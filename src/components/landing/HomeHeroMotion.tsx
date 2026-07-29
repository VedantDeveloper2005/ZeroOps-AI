"use client";

import { motion, useReducedMotion } from "framer-motion";
import { LockKeyhole } from "lucide-react";

const deploymentPath = [
  {
    label: "Source",
    value: "GitHub repository",
    state: "User selected",
  },
  {
    label: "Evidence",
    value: "Runtime and deployment facts",
    state: "Reviewable",
  },
  {
    label: "Plan",
    value: "Azure App Service",
    state: "Draft",
  },
  {
    label: "Execution",
    value: "Dedicated deployment worker",
    state: "Locked",
  },
] as const;

const easeOut = [0.22, 1, 0.36, 1] as const;

export function HomeHeroMotion() {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0.88, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: reduceMotion ? 0 : 0.38,
        ease: easeOut,
      }}
      className="relative overflow-hidden rounded-3xl border border-border bg-card p-2 shadow-[var(--shadow-md)]"
    >
      <motion.div
        aria-hidden="true"
        initial={reduceMotion ? false : { opacity: 0, scale: 0.9 }}
        animate={{ opacity: 0.7, scale: 1 }}
        transition={{
          delay: reduceMotion ? 0 : 0.12,
          duration: reduceMotion ? 0 : 0.7,
          ease: easeOut,
        }}
        className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-primary-glow blur-3xl"
      />

      <div className="relative rounded-[1.15rem] border border-border bg-background-secondary/85">
        <div className="flex flex-col gap-3 border-b border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold">Deployment path</p>
            <p className="mt-0.5 text-xs text-foreground-muted">
              The decision stays visible from intake to execution.
            </p>
          </div>
          <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-warning/25 bg-warning-subtle px-2.5 py-1 text-[11px] font-semibold text-warning">
            <LockKeyhole aria-hidden="true" size={12} />
            Approval required
          </span>
        </div>

        <ol
          aria-label="Illustrated deployment path"
          className="p-4 sm:p-5"
        >
          {deploymentPath.map((item, index) => (
            <motion.li
              key={item.label}
              initial={
                reduceMotion
                  ? false
                  : {
                      opacity: 0.72,
                      y: 8,
                    }
              }
              animate={{ opacity: 1, y: 0 }}
              transition={{
                delay: reduceMotion ? 0 : 0.12 + index * 0.08,
                duration: reduceMotion ? 0 : 0.32,
                ease: easeOut,
              }}
              className="relative grid grid-cols-[2.25rem_minmax(0,1fr)] gap-3 pb-4 last:pb-0"
            >
              {index < deploymentPath.length - 1 && (
                <>
                  <span
                    aria-hidden="true"
                    className="absolute left-[1.08rem] top-8 h-[calc(100%-1rem)] w-px bg-border"
                  />
                  <motion.span
                    aria-hidden="true"
                    initial={reduceMotion ? false : { scaleY: 0 }}
                    animate={{ scaleY: 1 }}
                    transition={{
                      delay: reduceMotion ? 0 : 0.2 + index * 0.1,
                      duration: reduceMotion ? 0 : 0.45,
                      ease: easeOut,
                    }}
                    className="absolute left-[1.08rem] top-8 h-[calc(100%-1rem)] w-px origin-top bg-gradient-to-b from-primary via-primary/50 to-transparent"
                  />
                </>
              )}

              <motion.span
                initial={reduceMotion ? false : { scale: 0.92 }}
                animate={{ scale: 1 }}
                transition={{
                  delay: reduceMotion ? 0 : 0.16 + index * 0.08,
                  duration: reduceMotion ? 0 : 0.28,
                  ease: easeOut,
                }}
                className="relative z-10 grid h-9 w-9 place-items-center rounded-xl border border-primary/25 bg-card font-mono text-xs font-semibold text-primary shadow-sm"
              >
                {index + 1}
              </motion.span>

              <div className="flex min-w-0 flex-col gap-2 rounded-xl border border-border bg-card/95 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-foreground-subtle">
                    {item.label}
                  </p>
                  <p className="mt-1 text-sm font-semibold text-foreground">
                    {item.value}
                  </p>
                </div>
                <span className="w-fit shrink-0 rounded-full bg-surface-subtle px-2 py-1 text-[10px] font-semibold text-foreground-muted">
                  {item.state}
                </span>
              </div>
            </motion.li>
          ))}
        </ol>

        <p className="border-t border-border px-5 py-3 text-[11px] leading-5 text-foreground-subtle">
          Workflow illustration. No cloud action runs before approval.
        </p>
      </div>
    </motion.div>
  );
}
