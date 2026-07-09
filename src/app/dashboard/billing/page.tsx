"use client";

import { motion } from "framer-motion";
import { Check, CreditCard, ExternalLink, Loader2, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, type BillingOperation, type UserProfile } from "@/lib/api";
import { useNotifications } from "@/lib/NotificationContext";

const formatMoney = (amountCents: number, currency: string) => {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
  }).format(amountCents / 100);
};

const formatDate = (value?: string | null) => {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

const statusClass = (status: string) => {
  switch (status) {
    case "paid":
      return "bg-success/15 text-success border-success/25";
    case "consumed":
      return "bg-primary/15 text-primary border-primary/25";
    case "pending_payment":
      return "bg-warning/15 text-warning border-warning/25";
    default:
      return "bg-muted text-foreground-muted border-border";
  }
};

export default function BillingPage() {
  const { addToast } = useNotifications();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [operations, setOperations] = useState<BillingOperation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [checkoutOperationId, setCheckoutOperationId] = useState<string | null>(null);

  useEffect(() => {
    async function loadBilling() {
      setIsLoading(true);
      try {
        const [profileRes, opsRes] = await Promise.allSettled([
          api.getProfile(),
          api.getBillingOperations(),
        ]);
        if (profileRes.status === "fulfilled") setProfile(profileRes.value);
        if (opsRes.status === "fulfilled") setOperations(opsRes.value);
      } catch (err) {
        console.error("Failed to load billing data:", err);
      } finally {
        setIsLoading(false);
      }
    }
    loadBilling();
  }, []);

  const fullName = profile?.first_name
    ? `${profile.first_name} ${profile.last_name || ""}`.trim()
    : profile?.email || "Account holder";

  const planName = profile?.plan
    ? `${profile.plan.charAt(0).toUpperCase()}${profile.plan.slice(1)} Plan`
    : "Starter Plan";

  const totals = useMemo(() => {
    const pending = operations.filter((op) => op.status === "pending_payment");
    const paid = operations.filter((op) => op.status === "paid");
    const consumed = operations.filter((op) => op.status === "consumed");
    return { pending, paid, consumed };
  }, [operations]);

  const usageStats = [
    { name: "Deployment Records", value: String(profile?.total_deployments ?? 0), detail: "Stored in backend" },
    { name: "Active Deployments", value: String(profile?.active_deployments ?? 0), detail: "Currently running" },
    { name: "Paid AI Fixes", value: String(totals.paid.length + totals.consumed.length), detail: "Approved operations" },
    { name: "Pending Payments", value: String(totals.pending.length), detail: "Awaiting checkout" },
  ];

  const continueCheckout = async (operation: BillingOperation) => {
    setCheckoutOperationId(operation.id);
    try {
      const updated = await api.createBillingCheckout(operation.id);
      setOperations((prev) => prev.map((item) => item.id === operation.id ? { ...item, ...updated } : item));
      if (updated.checkout_url) {
        window.location.assign(updated.checkout_url);
        return;
      }
      addToast("Checkout is not available for the current payment provider.", "warning");
    } catch (err) {
      console.error("Failed to create checkout session:", err);
      addToast("Could not start checkout.", "error");
    } finally {
      setCheckoutOperationId(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="animate-spin text-primary" size={24} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-card border border-border rounded-xl p-6 relative overflow-hidden shadow-sm"
          >
            <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-3xl pointer-events-none" />

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <span className="text-[10px] px-2.5 py-1 rounded-full bg-primary/10 text-primary font-bold tracking-wide uppercase">
                  Current Subscription
                </span>
                <h3 className="text-2xl font-bold text-foreground mt-3">{planName}</h3>
                <p className="text-foreground-muted text-xs mt-1">
                  AI code changes are charged only after an explicit paid operation is created and approved.
                </p>
              </div>
              <div className="text-left sm:text-right">
                <p className="text-[10px] text-foreground-muted uppercase font-bold">Billing Identity</p>
                <p className="text-sm font-extrabold text-foreground mt-1">{fullName}</p>
              </div>
            </div>

            <div className="border-t border-border/60 my-5" />

            <div className="grid md:grid-cols-3 gap-4">
              {["Authenticated user billing", "Per-user cloud deployments", "Payment-gated AI code changes"].map((feature) => (
                <div key={feature} className="flex items-center gap-2 text-xs font-semibold text-foreground-muted">
                  <div className="w-5 h-5 rounded-full bg-success/15 flex items-center justify-center flex-shrink-0">
                    <Check size={12} className="text-success" />
                  </div>
                  <span>{feature}</span>
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="bg-card border border-border rounded-xl p-6 shadow-sm"
          >
            <h3 className="text-sm font-bold text-foreground mb-6 flex items-center gap-2">
              <TrendingUp size={16} className="text-primary" />
              Account Usage
            </h3>

            <div className="grid md:grid-cols-2 gap-4">
              {usageStats.map((stat) => (
                <div key={stat.name} className="p-4 rounded-xl bg-background-secondary border border-border/50 space-y-1">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-foreground-muted">{stat.name}</p>
                  <p className="text-2xl font-extrabold text-foreground">{stat.value}</p>
                  <p className="text-[10px] text-foreground-muted font-semibold">{stat.detail}</p>
                </div>
              ))}
            </div>
          </motion.div>
        </div>

        <div className="space-y-6">
          <motion.div
            initial={{ opacity: 0, x: 15 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 }}
            className="rounded-2xl p-5 bg-gradient-to-br from-zinc-900 to-zinc-950 text-white relative overflow-hidden shadow-xl min-h-44 flex flex-col justify-between border border-zinc-700/50"
          >
            <div className="absolute top-5 right-5 w-14 h-7 bg-white/10 rounded border border-white/20 backdrop-blur-md flex items-center justify-center font-bold text-[9px] uppercase tracking-widest text-white/70">
              ZeroOps
            </div>
            <div>
              <CreditCard size={28} className="text-white/80" />
              <p className="mt-6 text-sm font-bold text-white">Payment Method</p>
              <p className="text-xs text-white/55 mt-1 leading-relaxed">
                Checkout is handled by the configured payment provider. No card details are stored in this app.
              </p>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="bg-card border border-border rounded-xl p-5 shadow-sm"
          >
            <h3 className="text-sm font-bold text-foreground mb-4">Paid AI Operations</h3>
            <div className="space-y-3">
              {operations.length > 0 ? operations.map((operation) => (
                <div key={operation.id} className="p-3 rounded-lg bg-background-secondary border border-border/50 hover:bg-card transition space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-bold text-foreground">{operation.description || operation.operation_type.replaceAll("_", " ")}</p>
                      <p className="text-[10px] text-foreground-muted mt-0.5 font-semibold">{formatDate(operation.created_at)}</p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="text-xs font-bold text-foreground">{formatMoney(operation.amount_cents, operation.currency)}</p>
                      <span className={`text-[9px] px-1.5 py-0.5 rounded-full border font-bold uppercase mt-0.5 inline-block ${statusClass(operation.status)}`}>
                        {operation.status.replaceAll("_", " ")}
                      </span>
                    </div>
                  </div>
                  {operation.status === "pending_payment" && (
                    <button
                      onClick={() => continueCheckout(operation)}
                      disabled={checkoutOperationId === operation.id}
                      className="w-full px-3 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-xs font-bold transition cursor-pointer flex items-center justify-center gap-1.5 disabled:opacity-50"
                    >
                      {checkoutOperationId === operation.id ? (
                        <>
                          <Loader2 size={12} className="animate-spin" /> Starting checkout...
                        </>
                      ) : (
                        <>
                          Continue Checkout <ExternalLink size={12} />
                        </>
                      )}
                    </button>
                  )}
                </div>
              )) : (
                <div className="text-center py-8">
                  <p className="text-xs font-semibold text-foreground">No paid operations yet</p>
                  <p className="text-[11px] text-foreground-muted mt-1">
                    AI code fixes will appear here after a project requests one.
                  </p>
                </div>
              )}
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
