/** @type {import('next').NextConfig} */
const nextConfig = {
  /**
   * During local development, proxy /api/* requests to the FastAPI backend
   * running on port 8000. In production on Vercel, requests go directly to
   * the Python serverless function (vercel.json routes handle this).
   */
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination:
          process.env.NODE_ENV === "production"
            ? "/api/:path*"  // Vercel handles routing via vercel.json
            : "http://localhost:8000/api/:path*",
      },
    ];
  },
};

module.exports = nextConfig;
