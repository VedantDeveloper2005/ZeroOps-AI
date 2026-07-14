import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import { NotificationProvider } from "@/lib/NotificationContext";
import { AuthProvider } from "@/lib/AuthContext";
import { ToastContainer } from "@/components/ui/ToastContainer";
import { DeviceGate } from "@/components/DeviceGate";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ZeroOps — Ship without the platform overhead",
  description:
    "Connect a repository or upload your code. ZeroOps prepares and runs your application while you stay in control.",
  keywords: [
    "application deployment",
    "repository deployment",
    "cloud operations",
    "production readiness",
  ],
  openGraph: {
    title: "ZeroOps — Bring your code. Keep the control.",
    description:
      "Bring your code. Keep the control. Leave the platform work to ZeroOps.",
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
          defaultTheme="light"
          enableSystem={false}
          disableTransitionOnChange={false}
        >
          <NotificationProvider>
            <AuthProvider>
              <DeviceGate>
                <a href="#main-content" className="skip-link">Skip to main content</a>
                {children}
                <ToastContainer />
              </DeviceGate>
            </AuthProvider>
          </NotificationProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
