/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  deploymentId: process.env.DEPLOYMENT_VERSION || process.env.WEBSITE_SITE_NAME,
};

module.exports = nextConfig;
