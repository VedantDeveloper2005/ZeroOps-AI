export default function DashboardLoading() {
  return (
    <div role="status" className="flex min-h-[55vh] items-center justify-center gap-3 rounded-xl border border-border bg-card text-sm font-medium text-foreground-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-primary motion-reduce:animate-none" />
      Loading workspace…
    </div>
  );
}
