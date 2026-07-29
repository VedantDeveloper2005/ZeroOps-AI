import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { NotificationProvider } from "@/lib/NotificationContext";
import { AuthProvider } from "@/lib/AuthContext";
import { ToastContainer } from "@/components/ui/ToastContainer";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  applicationName: "ZeroOps AI",
  title: {
    default: "ZeroOps AI — Review before you deploy",
    template: "%s | ZeroOps AI",
  },
  description:
    "Import a GitHub repository or ZIP, review deterministic deployment evidence, approve an Azure App Service plan, and deploy through a dedicated worker.",
  keywords: [
    "Azure App Service deployment",
    "repository analysis",
    "approval-based deployment",
    "Azure deployment worker",
  ],
  openGraph: {
    title: "ZeroOps AI — Review before you deploy",
    description:
      "A review-first path from GitHub or ZIP source to an approved Azure App Service deployment.",
    siteName: "ZeroOps AI",
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "ZeroOps AI — Review before you deploy",
    description:
      "Import source, inspect repository evidence, approve the App Service plan, and deploy through a dedicated worker.",
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
      className={`${geistSans.variable} ${geistMono.variable}`}
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
