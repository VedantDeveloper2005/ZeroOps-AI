import { BarChart3, DatabaseZap } from "lucide-react";
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

      <StatePanel
        variant="disconnected"
        title="Azure cost data is not connected"
        description="The cost-optimization endpoint is intentionally unavailable until Azure Cost Management data can be read. No spend, savings, or rightsizing figures are shown."
      />

      <section
        aria-labelledby="cost-data-heading"
        className="mt-6 rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6"
      >
        <div className="flex gap-3">
          <DatabaseZap size={20} className="mt-0.5 shrink-0 text-primary" aria-hidden="true" />
          <div>
            <h2 id="cost-data-heading" className="text-sm font-semibold text-foreground">
              What is missing
            </h2>
            <p className="mt-1.5 max-w-2xl text-xs leading-5 text-foreground-muted">
              ZeroOps has no Azure billing import, resource-cost history, or usage-based savings model yet.
            </p>
          </div>
        </div>
        <div className="mt-5 flex gap-3 border-t border-border pt-5">
          <BarChart3 size={20} className="mt-0.5 shrink-0 text-foreground-subtle" aria-hidden="true" />
          <p className="text-xs leading-5 text-foreground-muted">
            This page will remain empty instead of presenting synthetic monthly totals or savings claims.
          </p>
        </div>
      </section>
    </div>
  );
}
