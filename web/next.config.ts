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
  // @huggingface/transformers loads onnxruntime-node at runtime, which the
  // route's file trace does not see. Include its JS and the Linux x64 native
  // runtime that the Vercel function executes, and nothing else.
  outputFileTracingIncludes: {
    "/api/ask": [
      "./node_modules/onnxruntime-node/package.json",
      "./node_modules/onnxruntime-node/dist/**/*",
      "./node_modules/onnxruntime-node/bin/napi-v6/linux/x64/**/*",
    ],
  },
};

export default nextConfig;
