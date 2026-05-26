import type { NextConfig } from "next";

<<<<<<< HEAD
const backendUrl =
  process.env.ZEROOPS_BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

const normalizedBackendUrl = backendUrl.replace(/\/$/, "");

const nextConfig: NextConfig = {
  deploymentId: process.env.DEPLOYMENT_VERSION || process.env.WEBSITE_SITE_NAME,
=======
const nextConfig: NextConfig = {
>>>>>>> 7a8a49ab91a776be547d07446a274f5d8f0822b2
  async rewrites() {
    return [
      {
        source: "/api/:path*",
<<<<<<< HEAD
        destination: `${normalizedBackendUrl}/api/:path*`,
      },
      {
        source: "/ws/:path*",
        destination: `${normalizedBackendUrl}/ws/:path*`,
=======
        destination: "http://localhost:8000/api/:path*",
      },
      {
        source: "/ws/:path*",
        destination: "http://localhost:8000/ws/:path*",
>>>>>>> 7a8a49ab91a776be547d07446a274f5d8f0822b2
      },
    ];
  },
};

export default nextConfig;
