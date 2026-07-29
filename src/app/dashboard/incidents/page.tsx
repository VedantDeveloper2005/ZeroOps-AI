"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Check, Copy, Loader2, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { useNotifications } from "@/lib/NotificationContext";
import { api, getErrorMessage, type Notification } from "@/lib/api";

function formatTimestamp(value: string | null) {
  if (!value) return "Time not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Time not recorded";
  return date.toLocaleString();
}

function eventTone(type: Notification["type"]) {
  if (type === "critical") return "border-l-danger";
  if (type === "warning") return "border-l-warning";
  if (type === "success") return "border-l-success";
  return "border-l-info";
}

export default function IncidentsPage() {
  const { addToast } = useNotifications();
  const [events, setEvents] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadEvents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setEvents(await api.getNotifications("incident"));
    } catch (requestError) {
      setEvents([]);
      setError(getErrorMessage(requestError, "Operational events could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadEvents();
  }, [loadEvents]);

  const acknowledge = async (event: Notification) => {
    if (event.read) return;
    setEvents((current) =>
      current.map((item) => (item.id === event.id ? { ...item, read: true } : item)),
    );
    try {
      await api.markNotificationRead(event.id);
    } catch (requestError) {
      setEvents((current) =>
        current.map((item) => (item.id === event.id ? { ...item, read: false } : item)),
      );
      addToast(getErrorMessage(requestError, "The event could not be acknowledged."), "error");
    }
  };

  const copyEvent = async (event: Notification) => {
    const report = [
      "ZEROOPS OPERATIONAL EVENT",
      `Event ID: ${event.id}`,
      `Recorded: ${formatTimestamp(event.created_at)}`,
      `Type: ${event.type}`,
      `Acknowledged: ${event.read ? "yes" : "no"}`,
      "",
      event.title,
      event.message,
    ].join("\n");

    try {
      await navigator.clipboard.writeText(report);
      addToast("Operational event copied.", "success");
    } catch {
      addToast("Clipboard access was not available.", "error");
    }
  };

  const unacknowledged = events.filter((event) => !event.read).length;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="Operational events"
        description="Backend notifications categorized as incidents. Acknowledging an event marks it read; it does not resolve an underlying service condition."
        actions={
          <button
            type="button"
            onClick={() => void loadEvents()}
            disabled={loading}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-semibold text-foreground shadow-sm hover:bg-surface-raised disabled:opacity-50"
          >
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        }
      />

      <div className="rounded-xl border border-info/25 bg-info-subtle px-4 py-3 text-xs leading-5 text-foreground">
        <strong className="font-semibold">{unacknowledged}</strong> unacknowledged event
        {unacknowledged === 1 ? "" : "s"}. ZeroOps does not currently run an independent incident lifecycle or resolution workflow.
      </div>

      {error ? (
        <StatePanel
          variant="error"
          title="Operational events are unavailable"
          description={error}
          action={{ label: "Try again", onClick: () => void loadEvents() }}
        />
      ) : loading ? (
        <div role="status" className="flex min-h-52 items-center justify-center gap-3 rounded-xl border border-border bg-card text-sm text-foreground-muted">
          <Loader2 size={18} className="animate-spin text-primary" />
          Loading recorded events…
        </div>
      ) : events.length === 0 ? (
        <StatePanel
          variant="empty"
          title="No operational events are recorded"
          description="This means the backend has not saved any incident-category notifications. It is not proof that the deployed service has had no incidents."
        />
      ) : (
        <section aria-label="Recorded operational events" className="space-y-3">
          {events.map((event) => (
            <article
              key={event.id}
              className={`rounded-xl border border-l-4 border-border bg-card p-4 shadow-sm ${eventTone(event.type)}`}
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <AlertTriangle size={15} className={event.type === "critical" ? "text-danger" : "text-warning"} />
                    <h2 className="text-sm font-semibold text-foreground">{event.title}</h2>
                    <span className="rounded-full border border-border bg-surface-subtle px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-foreground-muted">
                      {event.type}
                    </span>
                    <span className="rounded-full border border-border bg-surface-subtle px-2 py-0.5 text-[10px] font-medium text-foreground-muted">
                      {event.read ? "Acknowledged" : "Unacknowledged"}
                    </span>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-foreground-muted">{event.message}</p>
                  <p className="mt-2 text-[11px] text-foreground-subtle">{formatTimestamp(event.created_at)}</p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  {!event.read && (
                    <button
                      type="button"
                      onClick={() => void acknowledge(event)}
                      className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-[11px] font-semibold text-foreground hover:bg-surface-raised"
                    >
                      <Check size={14} />
                      Acknowledge
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void copyEvent(event)}
                    className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-[11px] font-semibold text-foreground hover:bg-surface-raised"
                  >
                    <Copy size={14} />
                    Copy
                  </button>
                </div>
              </div>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
