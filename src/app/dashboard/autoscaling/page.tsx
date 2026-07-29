import { Gauge, Settings2 } from "lucide-react";
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

      <StatePanel
        variant="info"
        title="Capacity changes are not available in ZeroOps"
        description="The backend does not currently apply replica or App Service plan changes. Manage paid capacity in Azure until this integration is implemented."
        action={{ label: "Review Azure connection", href: "/dashboard/settings" }}
      />

      <section
        aria-labelledby="capacity-boundary-heading"
        className="mt-6 grid gap-4 sm:grid-cols-2"
      >
        <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <Gauge size={20} className="text-primary" aria-hidden="true" />
          <h2 id="capacity-boundary-heading" className="mt-3 text-sm font-semibold text-foreground">
            No automatic scaling
          </h2>
          <p className="mt-1.5 text-xs leading-5 text-foreground-muted">
            ZeroOps does not infer traffic, choose replica counts, or change paid capacity.
          </p>
        </div>
        <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <Settings2 size={20} className="text-primary" aria-hidden="true" />
          <h2 className="mt-3 text-sm font-semibold text-foreground">
            Azure remains the control plane
          </h2>
          <p className="mt-1.5 text-xs leading-5 text-foreground-muted">
            Use the Azure portal or your existing infrastructure workflow for capacity changes.
          </p>
        </div>
      </section>
    </div>
  );
}
