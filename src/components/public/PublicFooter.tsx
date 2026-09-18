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
    <footer style={{ borderTop: "1px solid var(--border)", background: "var(--background-secondary)" }}>
      <div className="mx-auto grid w-full max-w-7xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-[1.2fr_2fr] lg:px-8 lg:py-16">
        <div className="max-w-sm">
          <BrandMark />
          <p className="mt-4 text-sm leading-6" style={{ color: "var(--foreground-subtle)" }}>
            A review-first path from repository evidence to an exact, approved
            Azure App Service release record.
          </p>
          <div className="mt-6 flex items-center gap-4">
            <a
              href="https://github.com/VedantDeveloper2005/ZeroOps-AI"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="ZeroOps AI on GitHub"
              className="grid h-9 w-9 place-items-center rounded-lg transition-all duration-200 hover:bg-[var(--surface-subtle)]"
              style={{ border: "1px solid var(--border)", color: "var(--foreground-subtle)" }}
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current" aria-hidden="true">
                <path d="M12 .7a11.5 11.5 0 0 0-3.64 22.4c.58.1.79-.25.79-.56v-2.23c-3.22.7-3.9-1.37-3.9-1.37-.53-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.04 1.77 2.71 1.26 3.38.96.1-.75.4-1.26.74-1.55-2.57-.3-5.27-1.29-5.27-5.69 0-1.26.45-2.28 1.18-3.08-.12-.29-.51-1.46.11-3.04 0 0 .96-.31 3.16 1.18a10.98 10.98 0 0 1 5.76 0c2.2-1.49 3.16-1.18 3.16-1.18.62 1.58.23 2.75.11 3.04.74.8 1.18 1.82 1.18 3.08 0 4.42-2.7 5.39-5.28 5.68.42.36.79 1.06.79 2.13v3.28c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .7Z" />
              </svg>
            </a>
          </div>
        </div>

        <div className="grid gap-8 sm:grid-cols-3">
          {footerGroups.map((group) => (
            <nav key={group.title} aria-label={`${group.title} links`}>
              <h2 className="text-xs font-semibold uppercase tracking-[0.14em]" style={{ color: "var(--foreground)" }}>
                {group.title}
              </h2>
              <ul className="mt-4 space-y-1">
                {group.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="inline-flex min-h-9 items-center text-sm transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                      style={{ color: "var(--foreground-subtle)" }}
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

      <div style={{ borderTop: "1px solid var(--border)" }}>
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-2 px-4 py-6 text-xs leading-5 sm:px-6 md:flex-row md:items-center md:justify-between lg:px-8" style={{ color: "var(--foreground-subtle)" }}>
          <p>&copy; {new Date().getFullYear()} ZeroOps AI.</p>
          <p>All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
}
