import type { NextConfig } from "next";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** FastAPI default; override with API_PROXY_TARGET if needed. */
const apiProxy = (process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  /** Hides the circular Next.js dev-tools button (bottom-left) that overlaps the sidebar. */
  devIndicators: false,
  outputFileTracingRoot: path.join(__dirname),
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "ik.imagekit.io", pathname: "/**" },
      { protocol: "https", hostname: "tailark.com", pathname: "/**" },
      { protocol: "https", hostname: "html.tailus.io", pathname: "/**" },
      { protocol: "https", hostname: "images.unsplash.com", pathname: "/**" },
    ],
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiProxy}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
