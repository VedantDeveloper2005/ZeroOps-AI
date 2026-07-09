/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  deploymentId: process.env.DEPLOYMENT_VERSION || process.env.WEBSITE_SITE_NAME,

  // Proxy /api/* and /ws/* to the backend App Service when ZEROOPS_BACKEND_URL
  // is configured.  This lets server-side rendering and middleware reach the
  // backend without exposing its origin to browsers.
  async rewrites() {
    const backendUrl = (process.env.ZEROOPS_BACKEND_URL || '').replace(/\/$/, '');
    if (!backendUrl) return [];
    return [
      { source: '/api/:path*', destination: `${backendUrl}/api/:path*` },
      { source: '/ws/:path*',  destination: `${backendUrl}/ws/:path*`  },
    ];
  },
};

module.exports = nextConfig;
