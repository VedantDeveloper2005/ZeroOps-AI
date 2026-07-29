"use client";

import { useNotifications } from "@/lib/NotificationContext";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { CheckCircle, AlertTriangle, AlertCircle, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

const toastStyles = {
  success: {
    label: "Success",
    panel: "border-success/25",
    iconTone: "bg-success-subtle text-success",
    icon: CheckCircle,
  },
  error: {
    label: "Error",
    panel: "border-danger/25",
    iconTone: "bg-danger-subtle text-danger",
    icon: AlertCircle,
  },
  warning: {
    label: "Warning",
    panel: "border-warning/25",
    iconTone: "bg-warning-subtle text-warning",
    icon: AlertTriangle,
  },
  info: {
    label: "Information",
    panel: "border-info/25",
    iconTone: "bg-info-subtle text-info",
    icon: Info,
  },
};

export function ToastContainer() {
  const { toasts, removeToast } = useNotifications();
  const shouldReduceMotion = useReducedMotion();

  return (
    <div
      aria-label="Notifications"
      className="pointer-events-none fixed inset-x-4 bottom-4 z-[90] flex flex-col gap-2 pb-[env(safe-area-inset-bottom)] sm:inset-x-auto sm:bottom-6 sm:right-6 sm:w-full sm:max-w-sm"
    >
      <AnimatePresence>
        {toasts.map((toast) => {
          const style = toastStyles[toast.type] || toastStyles.info;
          const Icon = style.icon;

          return (
            <motion.div
              key={toast.id}
              layout
              role={toast.type === "error" ? "alert" : "status"}
              aria-atomic="true"
              initial={
                shouldReduceMotion
                  ? { opacity: 0 }
                  : { opacity: 0, y: 16, scale: 0.98 }
              }
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={
                shouldReduceMotion
                  ? { opacity: 0 }
                  : {
                      opacity: 0,
                      y: 8,
                      scale: 0.98,
                      transition: { duration: 0.14 },
                    }
              }
              transition={{ duration: shouldReduceMotion ? 0 : 0.2, ease: "easeOut" }}
              className={cn(
                "pointer-events-auto flex items-start gap-3 rounded-xl border bg-card p-3 shadow-xl",
                style.panel,
              )}
            >
              <span
                className={cn(
                  "grid h-9 w-9 shrink-0 place-items-center rounded-lg",
                  style.iconTone,
                )}
              >
                <Icon size={18} aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1 py-1.5 text-sm font-medium leading-5 text-foreground">
                <span className="sr-only">{style.label}: </span>
                {toast.message}
              </div>
              <button
                type="button"
                onClick={() => removeToast(toast.id)}
                aria-label={`Dismiss ${style.label.toLowerCase()} notification`}
                className="grid min-h-11 min-w-11 shrink-0 place-items-center self-center rounded-lg text-foreground-muted transition-colors hover:bg-surface-raised hover:text-foreground"
              >
                <X size={16} aria-hidden="true" />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
