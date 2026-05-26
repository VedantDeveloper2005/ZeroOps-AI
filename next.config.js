const backendUrl =
  process.env.ZEROOPS_BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

const normalizedBackendUrl = backendUrl.replace(/\/$/, "");

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
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

module.exports = nextConfig;
