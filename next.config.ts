import type { NextConfig } from "next";

const backendUrl =
  process.env.ZEROOPS_BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

const normalizedBackendUrl = backendUrl.replace(/\/$/, "");

const nextConfig: NextConfig = {
  deploymentId: process.env.DEPLOYMENT_VERSION || process.env.WEBSITE_SITE_NAME,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${normalizedBackendUrl}/api/:path*`,
      },
      {
        source: "/ws/:path*",
        destination: `${normalizedBackendUrl}/ws/:path*`,
      },
    ];
  },
};

export default nextConfig;
