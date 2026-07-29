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
        "inline-flex min-h-11 items-center gap-2.5 rounded-lg text-foreground transition-opacity hover:opacity-80",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="relative grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary text-white shadow-sm"
      >
        <span className="h-3.5 w-3.5 rotate-45 rounded-[3px] border-[1.5px] border-white" />
        <span className="absolute h-1.5 w-1.5 rounded-[2px] bg-white" />
      </span>
      {!compact && (
        <span className="whitespace-nowrap text-[15px] font-semibold tracking-[-0.02em]">
          ZeroOps <span className="text-foreground-muted">AI</span>
        </span>
      )}
    </Link>
  );
}
