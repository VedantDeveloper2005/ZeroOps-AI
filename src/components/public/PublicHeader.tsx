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
        "inline-flex min-h-11 items-center rounded-lg px-3 text-sm font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        active
          ? "bg-primary-subtle text-primary"
          : "text-foreground-muted hover:bg-surface-subtle hover:text-foreground",
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
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/85">
      <div className="mx-auto flex min-h-16 w-full max-w-7xl items-center gap-3 px-4 sm:px-6 lg:px-8">
        <BrandMark />

        <nav
          aria-label="Primary navigation"
          className="ml-auto hidden items-center gap-1 lg:flex"
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

        <div className="ml-auto flex items-center gap-2 lg:ml-4">
          <Link
            href="/login"
            className="hidden min-h-11 items-center rounded-lg px-3 text-sm font-medium text-foreground-muted transition-colors hover:bg-surface-subtle hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary sm:inline-flex"
          >
            Sign in
          </Link>
          <Link
            href="/signup"
            aria-label="Create a workspace"
            className="inline-flex min-h-11 items-center justify-center rounded-lg bg-primary px-3.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background sm:px-4"
          >
            <span className="sm:hidden">Create</span>
            <span className="hidden sm:inline">Create workspace</span>
          </Link>

          <details ref={mobileMenuRef} className="group relative lg:hidden">
            <summary
              aria-label="Toggle navigation"
              className="grid min-h-11 min-w-11 cursor-pointer list-none place-items-center rounded-lg border border-border bg-card text-foreground transition-colors hover:bg-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary [&::-webkit-details-marker]:hidden"
            >
              <Menu aria-hidden="true" size={19} />
            </summary>
            <nav
              aria-label="Mobile navigation"
              className="absolute right-0 top-[calc(100%+0.6rem)] grid w-56 gap-1 rounded-xl border border-border bg-card p-2 shadow-xl"
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
              <div className="mt-1 border-t border-border pt-1 sm:hidden">
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
