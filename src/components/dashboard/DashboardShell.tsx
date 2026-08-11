"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { TopBar } from "@/components/dashboard/TopBar";

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const previousPathname = useRef(pathname);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem("zeroops:sidebar-collapsed");
    if (stored === "true") setSidebarCollapsed(true);
  }, []);

  useEffect(() => {
    setMobileNavigationOpen(false);
    if (previousPathname.current === pathname) return;

    previousPathname.current = pathname;
    const focusFrame = window.requestAnimationFrame(() => {
      document.getElementById("main-content")?.focus();
    });
    return () => window.cancelAnimationFrame(focusFrame);
  }, [pathname]);

  useEffect(() => {
    if (!mobileNavigationOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [mobileNavigationOpen]);

  const toggleSidebar = () => {
    setSidebarCollapsed((current) => {
      const next = !current;
      window.localStorage.setItem("zeroops:sidebar-collapsed", String(next));
      return next;
    });
  };

  return (
    <div className="dashboard-shell">
      <div className="flex min-h-dvh">
        <Sidebar
          collapsed={sidebarCollapsed}
          mobileOpen={mobileNavigationOpen}
          onMobileClose={() => setMobileNavigationOpen(false)}
          onToggle={toggleSidebar}
        />

        {mobileNavigationOpen && (
          <button
            type="button"
            aria-label="Close navigation"
            className="fixed inset-0 z-30 bg-slate-950/45 backdrop-blur-[2px] lg:hidden"
            onClick={() => setMobileNavigationOpen(false)}
          />
        )}

        <div className="dashboard-main-canvas">
          <TopBar
            navigationOpen={mobileNavigationOpen}
            onOpenNavigation={() => setMobileNavigationOpen(true)}
          />
          <main
            id="main-content"
            tabIndex={-1}
            className="dashboard-route px-4 pb-14 pt-6 outline-none sm:px-6 lg:px-8 lg:pt-8 xl:px-10"
          >
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
