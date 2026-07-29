import Link from "next/link";
import { BrandMark } from "@/components/BrandMark";

const footerGroups = [
  {
    title: "Product",
    links: [
      { label: "How it works", href: "/#workflow" },
      { label: "Documentation", href: "/docs" },
      { label: "Security", href: "/security" },
      { label: "Service status", href: "/status" },
      { label: "Contact", href: "/contact" },
    ],
  },
  {
    title: "Legal",
    links: [
      { label: "Privacy", href: "/privacy" },
      { label: "Terms", href: "/terms" },
      { label: "Acceptable use", href: "/acceptable-use" },
      { label: "Cookies", href: "/cookies" },
    ],
  },
  {
    title: "Data & trust",
    links: [
      { label: "Responsible disclosure", href: "/responsible-disclosure" },
      { label: "Data processing", href: "/data-processing" },
      { label: "Subprocessors", href: "/subprocessors" },
    ],
  },
] as const;

export function PublicFooter() {
  return (
    <footer className="border-t border-border bg-card/50">
      <div className="mx-auto grid w-full max-w-7xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-[1.2fr_2fr] lg:px-8 lg:py-14">
        <div className="max-w-sm">
          <BrandMark />
          <p className="mt-3 text-sm leading-6 text-foreground-muted">
            A review-first path from repository evidence to an approved Azure
            App Service deployment.
          </p>
        </div>

        <div className="grid gap-8 sm:grid-cols-3">
          {footerGroups.map((group) => (
            <nav key={group.title} aria-label={`${group.title} links`}>
              <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-foreground">
                {group.title}
              </h2>
              <ul className="mt-3 space-y-1">
                {group.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="inline-flex min-h-11 items-center text-sm text-foreground-muted transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
      </div>

      <div className="border-t border-border">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-2 px-4 py-5 text-xs leading-5 text-foreground-muted sm:px-6 md:flex-row md:items-center md:justify-between lg:px-8">
          <p>&copy; {new Date().getFullYear()} ZeroOps AI.</p>
          <p>Legal entity and registered-address details are pending legal review.</p>
        </div>
      </div>
    </footer>
  );
}
