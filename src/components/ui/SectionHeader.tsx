import type { ReactNode } from "react";

type SectionHeaderProps = {
  id?: string;
  title: string;
  description?: string;
  eyebrow?: string;
  actions?: ReactNode;
  className?: string;
};

export function SectionHeader({
  id,
  title,
  description,
  eyebrow,
  actions,
  className = "",
}: SectionHeaderProps) {
  return (
    <div className={`flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between ${className}`}>
      <div className="min-w-0 max-w-3xl">
        {eyebrow && <p className="ops-kicker mb-1.5">{eyebrow}</p>}
        <h2 id={id} className="text-lg font-semibold tracking-[-0.025em] text-foreground">
          {title}
        </h2>
        {description && (
          <p className="mt-1.5 text-sm leading-6 text-foreground-muted">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
