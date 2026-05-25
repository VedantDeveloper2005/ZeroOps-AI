"use client";

import * as React from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export function ThemeToggle({ collapsed = false }: { collapsed?: boolean }) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    const timer = setTimeout(() => {
      setMounted(true);
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  if (!mounted) return null;

  return (
    <button
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className={cn(
        "flex items-center p-2 rounded-lg hover:bg-card transition-colors text-foreground-muted hover:text-foreground",
        collapsed ? "justify-center w-full" : "w-full gap-3 px-3 py-2.5"
      )}
    >
      <div className="relative flex items-center justify-center w-5 h-5">
        <Sun className={cn("absolute transition-all", theme === "dark" ? "scale-0 opacity-0 -rotate-90" : "scale-100 opacity-100 rotate-0")} size={18} />
        <Moon className={cn("absolute transition-all", theme === "dark" ? "scale-100 opacity-100 rotate-0" : "scale-0 opacity-0 rotate-90")} size={18} />
      </div>
      {!collapsed && (
        <span className="text-sm font-medium">
          {theme === "dark" ? "Light Mode" : "Dark Mode"}
        </span>
      )}
    </button>
  );
}
