import { BarChart3, DatabaseZap, ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";

export default function CostOptimizationPage() {
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        eyebrow="FinOps"
        title="Cost optimization"
        description="Cost recommendations require measured billing data, not estimates."
      />

      <section className="overflow-hidden rounded-xl border border-warning/25 bg-card shadow-sm">
        <div className="flex flex-col gap-5 border-b border-border bg-warning-subtle px-5 py-5 sm:flex-row sm:items-start sm:px-6">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-warning/20 bg-card text-warning shadow-sm">
            <DatabaseZap size={20} aria-hidden="true" />
          </span>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-warning">
              Data boundary
            </p>
            <h2 className="mt-1 text-lg font-semibold tracking-[-0.02em] text-foreground">
              Azure cost data is not connected
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-foreground-muted">
              The cost endpoint remains unavailable until Azure Cost Management can provide
              measured billing records. No spend, savings, or rightsizing figures are inferred.
            </p>
          </div>
        </div>
        <div className="p-4 sm:p-5">
          <StatePanel
            compact
            variant="disconnected"
            title="No cost recommendation can be verified"
            description="Connect a measured billing source before treating any optimization recommendation as actionable."
          />
        </div>
      </section>

      <section
        aria-labelledby="cost-data-heading"
        className="mt-6 overflow-hidden rounded-xl border border-border bg-card shadow-sm"
      >
        <div className="flex gap-4 px-5 py-5 sm:px-6">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-primary-subtle text-primary">
            <DatabaseZap size={19} aria-hidden="true" />
          </span>
          <div>
            <h2 id="cost-data-heading" className="text-base font-semibold text-foreground">
              Required evidence
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-foreground-muted">
              ZeroOps has no Azure billing import, resource-cost history, or usage-based savings model yet.
            </p>
          </div>
        </div>
        <div className="grid border-t border-border sm:grid-cols-2 sm:divide-x sm:divide-border">
          <div className="flex gap-3 px-5 py-4 sm:px-6">
            <BarChart3 size={18} className="mt-0.5 shrink-0 text-foreground-subtle" aria-hidden="true" />
            <p className="text-sm leading-6 text-foreground-muted">
              No synthetic monthly totals or savings claims are displayed.
            </p>
          </div>
          <div className="flex gap-3 border-t border-border px-5 py-4 sm:border-t-0 sm:px-6">
            <ShieldCheck size={18} className="mt-0.5 shrink-0 text-success" aria-hidden="true" />
            <p className="text-sm leading-6 text-foreground-muted">
              Recommendations will require source, window, and resource evidence.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
