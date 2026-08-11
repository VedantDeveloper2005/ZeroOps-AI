import { Gauge, LockKeyhole, Settings2 } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";

export default function AutoscalingPage() {
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        eyebrow="Runtime"
        title="Capacity controls"
        description="Review the current availability of runtime scaling controls."
      />

      <section className="overflow-hidden rounded-xl border border-info/25 bg-card shadow-sm">
        <div className="flex flex-col gap-5 border-b border-border bg-info-subtle px-5 py-5 sm:flex-row sm:items-start sm:px-6">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-info/20 bg-card text-info shadow-sm">
            <LockKeyhole size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-info">
              Control boundary
            </p>
            <h2 className="mt-1 text-lg font-semibold tracking-[-0.02em] text-foreground">
              Capacity changes stay in Azure
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-foreground-muted">
              ZeroOps does not currently apply replica or App Service plan changes. Manage paid
              capacity in Azure until this integration is implemented.
            </p>
          </div>
        </div>
        <div className="p-4 sm:p-5">
          <StatePanel
            compact
            variant="info"
            title="No scaling action will be sent"
            description="This workspace can record deployment context, but it cannot infer demand or mutate paid runtime capacity."
            action={{ label: "Review Azure connection", href: "/dashboard/settings" }}
          />
        </div>
      </section>

      <section
        aria-labelledby="capacity-boundary-heading"
        className="mt-6 grid gap-4 sm:grid-cols-2"
      >
        <article className="rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-primary-subtle text-primary">
            <Gauge size={19} aria-hidden="true" />
          </span>
          <h2 id="capacity-boundary-heading" className="mt-4 text-base font-semibold text-foreground">
            No automatic scaling
          </h2>
          <p className="mt-2 text-sm leading-6 text-foreground-muted">
            ZeroOps does not infer traffic, choose replica counts, or change paid capacity.
          </p>
        </article>
        <article className="rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-surface-subtle text-foreground-muted">
            <Settings2 size={19} aria-hidden="true" />
          </span>
          <h2 className="mt-4 text-base font-semibold text-foreground">
            Azure remains the control plane
          </h2>
          <p className="mt-2 text-sm leading-6 text-foreground-muted">
            Use the Azure portal or your existing infrastructure workflow for capacity changes.
          </p>
        </article>
      </section>
    </div>
  );
}
