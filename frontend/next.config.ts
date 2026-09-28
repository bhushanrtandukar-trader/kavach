import type { NextConfig } from "next";

const isProd = process.env.NODE_ENV === "production";
const backend = process.env.KAVACH_BACKEND ?? "http://127.0.0.1:8050";

const config: NextConfig = {
  // Production is a static export that the Python server serves next to the API (one process, one port).
  output: isProd ? "export" : undefined,
  images: { unoptimized: true },
  reactStrictMode: true,
  poweredByHeader: false,
  // Development: `next dev` proxies /api to the Python server so the browser sees a single origin.
  ...(isProd
    ? {}
    : {
        async rewrites() {
          return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
        },
      }),
};

export default config;
