import type { Metadata } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import "./globals.css";
import { NotificationProvider } from "@/lib/NotificationContext";
import { AuthProvider } from "@/lib/AuthContext";
import { ToastContainer } from "@/components/ui/ToastContainer";

export const metadata: Metadata = {
  applicationName: "ZeroOps AI",
  title: {
    default: "ZeroOps AI — Review before you deploy",
    template: "%s | ZeroOps AI",
  },
  description:
    "Import a GitHub repository or ZIP, review recorded deployment evidence, and approve an exact Azure App Service release plan. Cloud execution remains prerequisite-dependent.",
  keywords: [
    "Azure App Service deployment",
    "repository analysis",
    "approval-based deployment",
    "Azure deployment worker",
  ],
  openGraph: {
    title: "ZeroOps AI — Review before you deploy",
    description:
      "A review-first MVP for commit-pinned evidence and exact Azure App Service release approval.",
    siteName: "ZeroOps AI",
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "ZeroOps AI — Review before you deploy",
    description:
      "Import source, inspect recorded evidence, and approve the exact App Service release plan.",
  },
  category: "developer tools",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      data-scroll-behavior="smooth"
      className={`${GeistSans.variable} ${GeistMono.variable}`}
    >
      <body className="min-h-screen bg-background text-foreground antialiased">
        <NotificationProvider>
          <AuthProvider>
            <a href="#main-content" className="skip-link">
              Skip to main content
            </a>
            {children}
            <ToastContainer />
          </AuthProvider>
        </NotificationProvider>
      </body>
    </html>
  );
}
