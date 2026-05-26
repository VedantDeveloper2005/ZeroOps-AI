"use client";

import { useNotifications } from "@/lib/NotificationContext";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle, AlertTriangle, AlertCircle, Info, X } from "lucide-react";

const toastStyles = {
  success: {
    bg: "bg-success/10 border-success/30 text-success glow-green-sm",
    icon: CheckCircle,
  },
  error: {
    bg: "bg-danger/10 border-danger/30 text-danger glow-red-sm",
    icon: AlertCircle,
  },
  warning: {
    bg: "bg-warning/10 border-warning/30 text-warning glow-yellow-sm",
    icon: AlertTriangle,
  },
  info: {
    bg: "bg-primary/10 border-primary/30 text-primary glow-blue-sm",
    icon: Info,
  },
};

export function ToastContainer() {
  const { toasts, removeToast } = useNotifications();

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-3 max-w-sm w-full pointer-events-none">
      <AnimatePresence>
        {toasts.map((toast) => {
          const style = toastStyles[toast.type] || toastStyles.info;
          const Icon = style.icon;

          return (
            <motion.div
              key={toast.id}
              layout
              initial={{ opacity: 0, y: 50, scale: 0.9 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.2 } }}
              className={`pointer-events-auto border rounded-xl p-4 flex gap-3 shadow-xl backdrop-blur-md ${style.bg}`}
            >
              <Icon size={18} className="flex-shrink-0 mt-0.5" />
              <div className="flex-1 text-sm font-medium text-foreground">
                {toast.message}
              </div>
              <button
                onClick={() => removeToast(toast.id)}
                className="text-foreground-muted hover:text-foreground p-0.5 self-start hover:bg-card-hover rounded-md transition-colors"
              >
                <X size={14} />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
