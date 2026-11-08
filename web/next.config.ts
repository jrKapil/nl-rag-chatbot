import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    resolveAlias: {
      "onnxruntime-node": "./lib/onnxruntime-node-shim.cjs",
    },
  },
};

export default nextConfig;
