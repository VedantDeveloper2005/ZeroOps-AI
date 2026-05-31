"use client";

import { useState, useEffect } from "react";
import { Monitor, Smartphone, Tablet, AlertCircle } from "lucide-react";

export default function MobileBlocker() {
  const [isMobileOrTablet, setIsMobileOrTablet] = useState(false);
  const [currentWidth, setCurrentWidth] = useState(0);

  useEffect(() => {
    const handleResize = () => {
      const width = window.innerWidth;
      setCurrentWidth(width);
      // 1024px is standard laptop/desktop breakpoint
      setIsMobileOrTablet(width < 1024);
    };

    // Run on mount
    handleResize();

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  if (!isMobileOrTablet) return null;

  return (
    <div className="fixed inset-0 z-[99999] flex flex-col items-center justify-center bg-zinc-950 text-white p-6 md:p-12 overflow-hidden select-none">
      {/* Background ambient glow */}
      <div className="absolute top-[-20%] left-[-20%] w-[60%] h-[60%] rounded-full bg-primary/10 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-20%] w-[60%] h-[60%] rounded-full bg-accent/10 blur-[120px] pointer-events-none" />

      {/* Main Card */}
      <div className="relative max-w-md w-full bg-zinc-900/80 backdrop-blur-xl border border-zinc-800 rounded-3xl p-8 md:p-10 shadow-2xl text-center space-y-8 animate-fade-in">
        {/* Device Icons Display */}
        <div className="flex items-center justify-center gap-6">
          <div className="relative p-4 bg-zinc-800/40 rounded-2xl border border-zinc-700/50 text-zinc-500 opacity-60">
            <Smartphone size={32} />
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-10 h-0.5 bg-red-500/80 rotate-45" />
            </div>
          </div>
          
          <div className="p-5 bg-primary/10 border border-primary/20 rounded-3xl text-primary animate-pulse shadow-lg shadow-primary/10">
            <Monitor size={48} />
          </div>

          <div className="relative p-4 bg-zinc-800/40 rounded-2xl border border-zinc-700/50 text-zinc-500 opacity-60">
            <Tablet size={32} />
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-10 h-0.5 bg-red-500/80 rotate-45" />
            </div>
          </div>
        </div>

        {/* Text Details */}
        <div className="space-y-3">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-zinc-800 border border-zinc-700 text-[10px] font-bold uppercase tracking-wider text-zinc-400">
            <AlertCircle size={12} className="text-primary" /> Desktop Experience Only
          </div>
          <h2 className="text-2xl font-extrabold tracking-tight text-white">
            Desktop Screen Required
          </h2>
          <p className="text-xs text-zinc-400 leading-relaxed">
            ZeroOps is a professional AI deployment and cloud orchestrator. Telemetry monitoring, multi-stage pipelines, and environment management require desktop-grade screen resolutions.
          </p>
        </div>

        {/* Warning Callout */}
        <div className="p-4 rounded-2xl bg-zinc-950/80 border border-zinc-800 text-left space-y-1 shadow-inner">
          <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block">Recommended Resolution:</span>
          <p className="text-xs text-zinc-300 font-medium">
            Width of 1024px or higher (currently: <span className="text-primary font-bold font-mono">{currentWidth}px</span>)
          </p>
        </div>

        {/* Brand Footer */}
        <div className="pt-2 text-[10px] font-bold text-zinc-600 tracking-widest uppercase">
          ZeroOps AI System
        </div>
      </div>
    </div>
  );
}
