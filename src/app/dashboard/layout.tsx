"use client";

import { useState } from "react";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { TopBar } from "@/components/dashboard/TopBar";
import { SystemHealthRibbon } from "@/components/dashboard/SystemHealthRibbon";
import { AIActionFeed } from "@/components/dashboard/AIActionFeed";
import { SubPageHeader } from "@/components/dashboard/SubPageHeader";
import { motion, AnimatePresence } from "framer-motion";
import { useNotifications } from "@/lib/NotificationContext";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [feedOpen, setFeedOpen] = useState(false);
  const { hasDeployed } = useNotifications();

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-background">
      {/* Only show system health ribbon after user has deployed */}
      {hasDeployed && <SystemHealthRibbon />}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} />
        <div className="flex-1 flex flex-col overflow-hidden">
          <TopBar feedOpen={feedOpen} onToggleFeed={() => setFeedOpen(!feedOpen)} />
          <div className="flex flex-1 overflow-hidden">
            <main className="flex-1 overflow-y-auto p-6">
              <AnimatePresence mode="wait">
                <motion.div
                  key={typeof window !== "undefined" ? window.location.pathname : "page"}
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.25, ease: "easeOut" }}
                >
                  <SubPageHeader />
                  {children}
                </motion.div>
              </AnimatePresence>
            </main>
            {/* Only show AI action feed after deployment */}
            {hasDeployed && <AIActionFeed isOpen={feedOpen} onClose={() => setFeedOpen(false)} />}
          </div>
        </div>
      </div>
    </div>
  );
}
