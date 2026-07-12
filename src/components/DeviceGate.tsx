"use client";

import { useState, useEffect } from "react";
import { Monitor, Smartphone, Tablet } from "lucide-react";

const MIN_DESKTOP_WIDTH = 1024;

export function DeviceGate({ children }: { children: React.ReactNode }) {
  const [isDesktop, setIsDesktop] = useState(true);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);

    const check = () => setIsDesktop(window.innerWidth >= MIN_DESKTOP_WIDTH);
    check();

    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  // Avoid hydration mismatch – render children on server
  if (!mounted) return <>{children}</>;

  if (isDesktop) return <>{children}</>;

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 p-6">
      {/* Subtle grid pattern */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,.15) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.15) 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }}
      />

      {/* Glow */}
      <div className="pointer-events-none absolute left-1/2 top-1/3 h-64 w-64 -translate-x-1/2 -translate-y-1/2 rounded-full bg-indigo-500/20 blur-[120px]" />

      <div className="relative flex max-w-md flex-col items-center text-center">
        {/* Device icons */}
        <div className="mb-8 flex items-end gap-4">
          <div className="flex flex-col items-center gap-2">
            <Smartphone className="h-8 w-8 text-red-400/70" />
            <div className="h-0.5 w-8 rounded-full bg-red-400/40" />
          </div>
          <div className="flex flex-col items-center gap-2">
            <Monitor className="h-12 w-12 text-emerald-400 drop-shadow-[0_0_12px_rgba(52,211,153,0.4)]" />
            <div className="h-0.5 w-12 rounded-full bg-emerald-400/60" />
          </div>
          <div className="flex flex-col items-center gap-2">
            <Tablet className="h-9 w-9 text-red-400/70" />
            <div className="h-0.5 w-9 rounded-full bg-red-400/40" />
          </div>
        </div>

        {/* Heading */}
        <h1 className="mb-3 text-2xl font-bold tracking-tight text-white">
          Desktop Only
        </h1>

        {/* Description */}
        <p className="mb-6 text-sm leading-relaxed text-slate-400">
          ZeroOps AI is built for a full desktop experience.
          <br />
          Please open this app on a <span className="font-medium text-white">laptop or desktop</span> with
          a screen width of at least <span className="font-mono text-indigo-300">1024px</span>.
        </p>

        {/* Badge */}
        <div className="inline-flex items-center gap-2 rounded-full border border-slate-700/60 bg-slate-800/60 px-4 py-2 text-xs text-slate-300 backdrop-blur-sm">
          <Monitor className="h-3.5 w-3.5 text-emerald-400" />
          Optimized for desktop browsers
        </div>
      </div>
    </div>
  );
}
