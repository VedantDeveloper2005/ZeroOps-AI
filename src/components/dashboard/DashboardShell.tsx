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

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <div className="flex min-h-dvh">
        <Sidebar
          collapsed={sidebarCollapsed}
          mobileOpen={mobileNavigationOpen}
          onMobileClose={() => setMobileNavigationOpen(false)}
          onToggle={() => setSidebarCollapsed((current) => !current)}
        />

        {mobileNavigationOpen && (
          <button
            type="button"
            aria-label="Close navigation"
            className="fixed inset-0 z-30 bg-slate-950/45 backdrop-blur-[2px] lg:hidden"
            onClick={() => setMobileNavigationOpen(false)}
          />
        )}

        <div className="min-w-0 flex-1">
          <TopBar onOpenNavigation={() => setMobileNavigationOpen(true)} />
          <main
            id="main-content"
            tabIndex={-1}
            className="mx-auto w-full max-w-[1600px] px-4 pb-12 pt-6 outline-none sm:px-6 lg:px-8 lg:pt-8"
          >
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
