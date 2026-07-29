import {
  CircleAlert,
  FileText,
  Info,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { PublicFooter } from "@/components/public/PublicFooter";
import {
  PublicHeader,
  type PublicSection,
} from "@/components/public/PublicHeader";

export type PublicPageSection = {
  id: string;
  title: string;
  paragraphs?: string[];
  bullets?: string[];
  note?: string;
};

export type PolicyPageProps = {
  eyebrow: string;
  title: string;
  description: string;
  current?: PublicSection;
  documentStatus?: string;
  lastUpdated?: string;
  notice?: string;
  noticeTone?: "neutral" | "caution";
  sections: PublicPageSection[];
};

function PageIcon({
  current,
  status,
}: {
  current?: PublicSection;
  status?: string;
}) {
  let Icon: LucideIcon = FileText;

  if (current === "security") Icon = ShieldCheck;
  if (current === "status") Icon = Info;
  if (status?.toLowerCase().includes("review")) Icon = CircleAlert;

  return (
    <span
      aria-hidden="true"
      className="grid h-11 w-11 place-items-center rounded-xl border border-primary/20 bg-primary-subtle text-primary"
    >
      <Icon aria-hidden="true" size={20} />
    </span>
  );
}

export function PolicyPage({
  eyebrow,
  title,
  description,
  current,
  documentStatus,
  lastUpdated,
  notice,
  noticeTone = "neutral",
  sections,
}: PolicyPageProps) {
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <PublicHeader current={current} />

      <main id="main-content">
        <header className="border-b border-border bg-card/35">
          <div className="mx-auto w-full max-w-7xl px-4 py-14 sm:px-6 sm:py-16 lg:px-8 lg:py-20">
            <PageIcon current={current} status={documentStatus} />
            <p className="mt-6 text-xs font-semibold uppercase tracking-[0.16em] text-primary">
              {eyebrow}
            </p>
            <h1 className="mt-3 max-w-4xl text-balance text-4xl font-semibold tracking-[-0.045em] sm:text-5xl">
              {title}
            </h1>
            <p className="mt-5 max-w-3xl text-pretty text-base leading-7 text-foreground-muted sm:text-lg">
              {description}
            </p>
            {(documentStatus || lastUpdated) && (
              <div className="mt-7 flex flex-wrap gap-x-5 gap-y-2 text-xs text-foreground-muted">
                {documentStatus && (
                  <span>
                    <span className="font-semibold text-foreground">Status:</span>{" "}
                    {documentStatus}
                  </span>
                )}
                {lastUpdated && (
                  <span>
                    <span className="font-semibold text-foreground">
                      Last updated:
                    </span>{" "}
                    {lastUpdated}
                  </span>
                )}
              </div>
            )}
          </div>
        </header>

        <div className="mx-auto grid w-full max-w-7xl gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-16 lg:px-8 lg:py-16">
          <aside className="lg:sticky lg:top-24 lg:self-start">
            <nav aria-label="On this page">
              <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-foreground">
                On this page
              </h2>
              <ul className="mt-3 grid gap-1 sm:grid-cols-2 lg:grid-cols-1">
                {sections.map((section) => (
                  <li key={section.id}>
                    <a
                      href={`#${section.id}`}
                      className="inline-flex min-h-10 w-full items-center rounded-lg px-2 text-sm text-foreground-muted transition-colors hover:bg-surface-subtle hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      {section.title}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          </aside>

          <div className="min-w-0 max-w-3xl">
            {notice && (
              <div
                className={[
                  "mb-10 rounded-xl border p-4 text-sm leading-6",
                  noticeTone === "caution"
                    ? "border-warning/30 bg-warning-subtle text-foreground"
                    : "border-border bg-surface-subtle text-foreground-muted",
                ].join(" ")}
                role="note"
              >
                <span className="font-semibold text-foreground">
                  Important:
                </span>{" "}
                {notice}
              </div>
            )}

            <div className="space-y-12">
              {sections.map((section) => (
                <section
                  key={section.id}
                  id={section.id}
                  className="scroll-mt-24"
                >
                  <h2 className="text-2xl font-semibold tracking-[-0.025em] text-foreground">
                    {section.title}
                  </h2>
                  {section.paragraphs?.map((paragraph) => (
                    <p
                      key={paragraph}
                      className="mt-4 text-base leading-7 text-foreground-muted"
                    >
                      {paragraph}
                    </p>
                  ))}
                  {section.bullets && (
                    <ul className="mt-4 space-y-3">
                      {section.bullets.map((bullet) => (
                        <li
                          key={bullet}
                          className="flex gap-3 text-base leading-7 text-foreground-muted"
                        >
                          <span
                            aria-hidden="true"
                            className="mt-[0.72rem] h-1.5 w-1.5 shrink-0 rounded-full bg-primary"
                          />
                          <span>{bullet}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {section.note && (
                    <p className="mt-5 border-l-2 border-primary pl-4 text-sm leading-6 text-foreground-muted">
                      {section.note}
                    </p>
                  )}
                </section>
              ))}
            </div>
          </div>
        </div>
      </main>

      <PublicFooter />
    </div>
  );
}
