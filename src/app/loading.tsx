export default function Loading() {
  return (
    <main id="main-content" className="grid min-h-dvh place-items-center bg-background px-6">
      <div role="status" className="flex items-center gap-3 text-sm font-medium text-foreground-muted">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-primary motion-reduce:animate-none" />
        Loading ZeroOps…
      </div>
    </main>
  );
}
