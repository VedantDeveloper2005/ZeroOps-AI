"use client";

import { Sliders, TrendingUp } from "lucide-react";
import { LockedView } from "@/components/dashboard/LockedView";
import { useNotifications } from "@/lib/NotificationContext";

export default function AutoscalingPage() {
  const { hasDeployed } = useNotifications();

  if (!hasDeployed) return <LockedView featureName="Capacity controls" />;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="rounded-2xl border border-border bg-card p-7 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="rounded-xl border border-primary/20 bg-primary/10 p-3 text-primary"><Sliders size={22} /></div>
          <div>
            <h1 className="text-lg font-extrabold text-foreground">Capacity controls</h1>
            <p className="text-xs text-foreground-muted">Simple, account-level control for your application runtime.</p>
          </div>
        </div>
        <div className="mt-6 rounded-xl border border-border bg-background-secondary/50 p-5 text-sm text-foreground-muted">
          Capacity is selected through the Azure App Service plan connected to your account. ZeroOps does not guess usage, set replica counts, or change paid capacity automatically.
        </div>
      </div>
      <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
        <div className="flex gap-3"><TrendingUp className="mt-0.5 text-primary" size={18} /><div><h2 className="text-sm font-bold text-foreground">When this becomes available</h2><p className="mt-1 text-xs leading-relaxed text-foreground-muted">After Azure hosting and real cost telemetry are connected, this page will show measured recommendations before any account-level capacity change is requested.</p></div></div>
      </div>
    </div>
  );
}
