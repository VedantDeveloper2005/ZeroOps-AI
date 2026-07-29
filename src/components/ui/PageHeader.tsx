import type { ReactNode } from "react";

type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
};

export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  return (
    <div className="mb-7 flex flex-col gap-4 border-b border-border pb-6 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0 max-w-3xl">
        {eyebrow && (
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.1em] text-primary">{eyebrow}</p>
        )}
        <h1 className="text-balance text-2xl font-semibold tracking-[-0.035em] text-foreground sm:text-[2rem]">
          {title}
        </h1>
        {description && (
          <p className="mt-2 max-w-2xl text-sm leading-6 text-foreground-muted">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
