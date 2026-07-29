"use client";

import { useCallback, useEffect, useState } from "react";
import { CreditCard, ExternalLink, Loader2, ReceiptText } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { api, getErrorMessage, type BillingOperation } from "@/lib/api";
import { useNotifications } from "@/lib/NotificationContext";

const formatMoney = (amountCents: number, currency: string) => {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: currency.toUpperCase(),
    }).format(amountCents / 100);
  } catch {
    return `${(amountCents / 100).toFixed(2)} ${currency.toUpperCase()}`;
  }
};

const formatDate = (value: string | null) => {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
};

const operationLabel = (value: string) =>
  value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

const statusClass = (status: string) => {
  switch (status) {
    case "paid":
      return "border-success/25 bg-success-subtle text-success";
    case "consumed":
      return "border-primary/25 bg-primary-subtle text-primary";
    case "pending_payment":
      return "border-warning/25 bg-warning-subtle text-warning";
    default:
      return "border-border bg-surface-subtle text-foreground-muted";
  }
};

export default function BillingPage() {
  const { addToast } = useNotifications();
  const [operations, setOperations] = useState<BillingOperation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [checkoutOperationId, setCheckoutOperationId] = useState<string | null>(null);

  const loadOperations = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      setOperations(await api.getBillingOperations());
    } catch (loadError) {
      setError(getErrorMessage(loadError, "Billing operations could not be loaded. Try again."));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadOperations();
  }, [loadOperations]);

  const continueCheckout = async (operation: BillingOperation) => {
    setCheckoutOperationId(operation.id);
    try {
      const updated = await api.createBillingCheckout(operation.id);
      setOperations((current) =>
        current.map((item) => (item.id === operation.id ? { ...item, ...updated } : item)),
      );
      if (!updated.checkout_url) {
        addToast("The configured payment provider did not return a checkout link.", "warning");
        return;
      }

      window.location.assign(updated.checkout_url);
    } catch (checkoutError) {
      addToast(getErrorMessage(checkoutError, "Checkout could not be started."), "error");
    } finally {
      setCheckoutOperationId(null);
    }
  };

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        eyebrow="Account"
        title="Billing operations"
        description="A record of on-demand paid operations returned by the configured payment backend. This is not a subscription or invoice view."
      />

      {isLoading ? (
        <div
          role="status"
          className="flex min-h-64 items-center justify-center rounded-xl border border-border bg-card"
        >
          <Loader2 size={22} className="animate-spin text-primary" aria-hidden="true" />
          <span className="ml-3 text-sm text-foreground-muted">Loading billing operations…</span>
        </div>
      ) : error ? (
        <StatePanel
          variant="error"
          title="Billing data is unavailable"
          description={error}
          action={{ label: "Try again", onClick: () => void loadOperations() }}
        />
      ) : operations.length === 0 ? (
        <StatePanel
          title="No paid operations"
          description="No payment-gated operation has been created for this account."
        />
      ) : (
        <section aria-labelledby="operation-history-heading" className="space-y-3">
          <div className="flex items-center gap-2">
            <ReceiptText size={18} className="text-primary" aria-hidden="true" />
            <h2 id="operation-history-heading" className="text-sm font-semibold text-foreground">
              Operation history
            </h2>
          </div>

          <ul className="space-y-3">
            {operations.map((operation) => {
              const isCheckingOut = checkoutOperationId === operation.id;
              return (
                <li
                  key={operation.id}
                  className="rounded-xl border border-border bg-card p-4 shadow-sm sm:p-5"
                >
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <CreditCard size={16} className="text-primary" aria-hidden="true" />
                        <h3 className="text-sm font-semibold text-foreground">
                          {operation.description?.trim() || operationLabel(operation.operation_type)}
                        </h3>
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${statusClass(operation.status)}`}
                        >
                          {operationLabel(operation.status)}
                        </span>
                      </div>
                      <dl className="mt-3 grid gap-x-8 gap-y-2 text-xs sm:grid-cols-2">
                        <div>
                          <dt className="text-foreground-muted">Created</dt>
                          <dd className="mt-0.5 text-foreground">{formatDate(operation.created_at)}</dd>
                        </div>
                        <div>
                          <dt className="text-foreground-muted">Payment provider</dt>
                          <dd className="mt-0.5 text-foreground">
                            {operation.provider ? operationLabel(operation.provider) : "Not reported"}
                          </dd>
                        </div>
                      </dl>
                    </div>

                    <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
                      <p className="font-mono text-base font-semibold tabular-nums text-foreground">
                        {formatMoney(operation.amount_cents, operation.currency)}
                      </p>
                      {operation.status === "pending_payment" && (
                        <button
                          type="button"
                          onClick={() => void continueCheckout(operation)}
                          disabled={isCheckingOut}
                          className="ops-primary min-w-40 disabled:opacity-60"
                        >
                          {isCheckingOut ? (
                            <>
                              <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                              Starting checkout…
                            </>
                          ) : (
                            <>
                              Continue checkout
                              <ExternalLink size={15} aria-hidden="true" />
                            </>
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}
