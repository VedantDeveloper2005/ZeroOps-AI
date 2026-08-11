import type { ReactNode } from "react";

type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
};

export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  return (
    <header className="ops-surface relative mb-8 overflow-hidden p-5 sm:p-6">
      <span aria-hidden="true" className="absolute inset-y-0 left-0 w-1 bg-primary" />
      <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0 max-w-3xl">
        {eyebrow && (
          <p className="ops-kicker mb-2">{eyebrow}</p>
        )}
        <h1 className="text-balance text-2xl font-semibold tracking-[-0.04em] text-foreground sm:text-[2rem] lg:text-[2.15rem]">
          {title}
        </h1>
        {description && (
          <p className="mt-2.5 max-w-2xl text-sm leading-6 text-foreground-muted">{description}</p>
        )}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}
