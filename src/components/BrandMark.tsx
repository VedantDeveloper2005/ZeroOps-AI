import Link from "next/link";
import { cn } from "@/lib/utils";

type BrandMarkProps = {
  href?: string;
  compact?: boolean;
  className?: string;
};

export function BrandMark({ href = "/", compact = false, className }: BrandMarkProps) {
  return (
    <Link
      href={href}
      aria-label="ZeroOps AI home"
      className={cn(
        "inline-flex min-h-11 items-center gap-2.5 rounded-lg text-foreground transition-opacity hover:opacity-90 group",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white font-bold shadow-lg shadow-blue-500/25 border border-blue-400/30 transition-transform group-hover:scale-105"
      >
        <svg
          className="w-4.5 h-4.5 text-white"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2.5"
          viewBox="0 0 24 24"
        >
          <path d="M12 2L2 7l10 5 10-5-10-5z" />
          <path d="M2 17l10 5 10-5" />
          <path d="M2 12l10 5 10-5" />
        </svg>
      </span>
      {!compact && (
        <span className="whitespace-nowrap text-[16px] font-bold tracking-tight" style={{ color: "var(--foreground)" }}>
          ZeroOps <span className="font-semibold text-blue-500">AI</span>
        </span>
      )}
    </Link>
  );
}
