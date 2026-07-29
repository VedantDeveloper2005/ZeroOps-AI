/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  deploymentId: process.env.DEPLOYMENT_VERSION || process.env.WEBSITE_SITE_NAME,

  async headers() {
    const production = process.env.NODE_ENV === 'production';
    const securityHeaders = [
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'X-Frame-Options', value: 'DENY' },
      { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
      { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=(), payment=(), browsing-topics=()' },
      { key: 'X-DNS-Prefetch-Control', value: 'off' },
      {
        key: 'Content-Security-Policy',
        value: "default-src 'self'; script-src 'self' 'unsafe-inline'" + (production ? '' : " 'unsafe-eval'") + "; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' https://d8j0ntlcm91z4.cloudfront.net; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; upgrade-insecure-requests",
      },
    ];
    if (production) {
      securityHeaders.push({ key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' });
    }
    return [{ source: '/:path*', headers: securityHeaders }];
  },

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
