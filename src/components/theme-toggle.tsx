"use client";

import * as React from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
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
      aria-label={theme === "dark" ? "Use light mode" : "Use dark mode"}
      title={theme === "dark" ? "Use light mode" : "Use dark mode"}
      className={cn(
        "min-h-11 flex items-center p-2 rounded-lg hover:bg-background-secondary transition-colors text-foreground-muted hover:text-foreground",
        collapsed ? "justify-center w-full" : "w-full gap-3 px-3 py-2.5"
      )}
    >
      <div className="relative flex items-center justify-center w-5 h-5">
        <Sun className={cn("absolute transition-all", theme === "dark" ? "scale-0 opacity-0 -rotate-90" : "scale-100 opacity-100 rotate-0")} size={18} />
        <Moon className={cn("absolute transition-all", theme === "dark" ? "scale-100 opacity-100 rotate-0" : "scale-0 opacity-0 rotate-90")} size={18} />
      </div>
      {!collapsed && (
        <span className="text-sm font-medium">
          {theme === "dark" ? "Use light mode" : "Use dark mode"}
        </span>
      )}
    </button>
  );
}
