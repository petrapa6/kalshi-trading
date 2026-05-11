import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  output: "standalone",
  // Trace from the monorepo root so pnpm-hoisted node_modules end up in
  // .next/standalone/node_modules/ instead of being missed.
  outputFileTracingRoot: path.join(__dirname, ".."),
};

export default nextConfig;
