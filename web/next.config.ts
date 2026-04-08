import type { NextConfig } from "next";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * `/api/*` is proxied at request time by `src/app/api/[...path]/route.ts` so Render can use
 * API_PROXY_TARGET from **runtime** env without rebuilding. (Build-time rewrites froze the wrong URL.)
 */
const nextConfig: NextConfig = {
  async redirects() {
    return [{ source: "/live-lab", destination: "/live-test", permanent: true }];
  },
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
};

export default nextConfig;
