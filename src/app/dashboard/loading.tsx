export default function DashboardLoading() {
  return (
    <div role="status" className="ops-surface flex min-h-[55vh] flex-col items-center justify-center px-6 text-center">
      <span className="grid h-12 w-12 place-items-center rounded-xl border border-primary/20 bg-primary-subtle">
        <span className="h-5 w-5 animate-spin rounded-full border-2 border-primary/25 border-t-primary motion-reduce:animate-none" />
      </span>
      <p className="mt-4 text-sm font-semibold text-foreground">Loading workspace</p>
      <p className="mt-1 text-xs text-foreground-muted">Checking recorded projects and release activity.</p>
    </div>
  );
}
