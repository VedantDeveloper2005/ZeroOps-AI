import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import { NotificationProvider } from "@/lib/NotificationContext";
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
  title: "ZeroOps — The Operating System for Autonomous Cloud Infrastructure",
  description:
    "Deploy production-grade applications instantly with AI. ZeroOps autonomously analyzes, secures, deploys, scales, and manages your applications on Kubernetes without DevOps complexity.",
  keywords: [
    "AI deployment",
    "Kubernetes",
    "DevOps automation",
    "cloud infrastructure",
    "AKS",
    "autonomous deployment",
  ],
  openGraph: {
    title: "ZeroOps — Deploy with AI",
    description:
      "The autonomous cloud deployment platform. Zero DevOps required.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable}`}
      suppressHydrationWarning
    >
      <body className="min-h-screen bg-background text-foreground antialiased transition-colors duration-300">
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange={false}
        >
          <NotificationProvider>
            {children}
            <ToastContainer />
          </NotificationProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

