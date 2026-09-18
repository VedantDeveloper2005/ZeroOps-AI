"use client";

import Link from "next/link";
import { Menu } from "lucide-react";
import { useRef } from "react";
import { BrandMark } from "@/components/BrandMark";

export type PublicSection =
  | "home"
  | "security"
  | "docs"
  | "status"
  | "contact"
  | "legal";

type PublicHeaderProps = {
  current?: PublicSection;
};

const navigation = [
  { label: "How it works", href: "/#workflow", section: "home" },
  { label: "Security", href: "/security", section: "security" },
  { label: "Docs", href: "/docs", section: "docs" },
  { label: "Status", href: "/status", section: "status" },
] satisfies Array<{
  label: string;
  href: string;
  section: PublicSection;
}>;

function HeaderLink({
  href,
  label,
  active,
  onNavigate,
}: {
  href: string;
  label: string;
  active: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={[
        "inline-flex min-h-10 items-center rounded-lg px-3 text-sm font-medium transition-all duration-200",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
        active
          ? "bg-blue-500/10 text-blue-400"
          : "text-[var(--foreground-muted)] hover:bg-[var(--surface-subtle)] hover:text-[var(--foreground)]",
      ].join(" ")}
    >
      {label}
    </Link>
  );
}

export function PublicHeader({ current }: PublicHeaderProps) {
  const mobileMenuRef = useRef<HTMLDetailsElement>(null);
  const closeMobileMenu = () => {
    if (mobileMenuRef.current) {
      mobileMenuRef.current.open = false;
    }
  };

  return (
    <header
      className="sticky top-0 z-40 backdrop-blur-xl"
      style={{
        borderBottom: "1px solid var(--border)",
        background: "color-mix(in srgb, var(--background) 80%, transparent)",
      }}
    >
      <div className="mx-auto flex min-h-16 w-full max-w-7xl items-center gap-3 px-4 sm:px-6 lg:px-8">
        <BrandMark />

        <nav
          aria-label="Primary navigation"
          className="ml-auto hidden items-center gap-0.5 lg:flex"
        >
          {navigation.map((item) => (
            <HeaderLink
              key={item.href}
              href={item.href}
              label={item.label}
              active={current === item.section}
            />
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-3 lg:ml-4">
          <Link
            href="/login"
            className="hidden min-h-10 items-center rounded-lg px-3.5 text-sm font-medium transition-all duration-200 sm:inline-flex"
            style={{ color: "var(--foreground-muted)" }}
          >
            Sign in
          </Link>
          <Link
            href="/signup"
            aria-label="Get started"
            className="inline-flex min-h-10 items-center justify-center rounded-xl bg-blue-600 px-4 text-sm font-semibold text-white shadow-lg shadow-blue-500/20 transition-all duration-200 hover:bg-blue-500 hover:shadow-blue-500/30 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <span className="sm:hidden">Start</span>
            <span className="hidden sm:inline">Get started</span>
          </Link>

          <details ref={mobileMenuRef} className="group relative lg:hidden">
            <summary
              aria-label="Toggle navigation"
              className="grid min-h-10 min-w-10 cursor-pointer list-none place-items-center rounded-lg transition-colors [&::-webkit-details-marker]:hidden"
              style={{ border: "1px solid var(--border)", background: "var(--card)", color: "var(--foreground)" }}
            >
              <Menu aria-hidden="true" size={18} />
            </summary>
            <nav
              aria-label="Mobile navigation"
              className="absolute right-0 top-[calc(100%+0.5rem)] grid w-56 gap-0.5 rounded-xl p-2 shadow-xl backdrop-blur-xl"
              style={{ border: "1px solid var(--border)", background: "var(--card)" }}
            >
              {navigation.map((item) => (
                <HeaderLink
                  key={item.href}
                  href={item.href}
                  label={item.label}
                  active={current === item.section}
                  onNavigate={closeMobileMenu}
                />
              ))}
              <div className="mt-1 pt-1 sm:hidden" style={{ borderTop: "1px solid var(--border)" }}>
                <HeaderLink
                  href="/login"
                  label="Sign in"
                  active={false}
                  onNavigate={closeMobileMenu}
                />
              </div>
            </nav>
          </details>
        </div>
      </div>
    </header>
  );
}
