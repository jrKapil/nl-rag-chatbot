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
  // route's file trace does not see. Include onnxruntime-node and its runtime
  // dependencies (both CJS and ESM builds), plus the Linux x64 native runtime
  // that the Vercel function executes, and nothing else.
  outputFileTracingIncludes: {
    "/api/ask": [
      "./node_modules/onnxruntime-node/package.json",
      "./node_modules/onnxruntime-node/dist/**/*",
      "./node_modules/onnxruntime-node/bin/napi-v6/linux/x64/**/*",
      "./node_modules/onnxruntime-common/**/*",
      "./node_modules/adm-zip/**/*",
      "./node_modules/global-agent/**/*",
      "./node_modules/globalthis/**/*",
      "./node_modules/matcher/**/*",
      "./node_modules/escape-string-regexp/**/*",
      "./node_modules/serialize-error/**/*",
      "./node_modules/type-fest/**/*",
      "./node_modules/semver/**/*",
      "./node_modules/define-properties/**/*",
      "./node_modules/define-data-property/**/*",
      "./node_modules/es-define-property/**/*",
      "./node_modules/es-errors/**/*",
      "./node_modules/gopd/**/*",
      "./node_modules/has-property-descriptors/**/*",
      "./node_modules/object-keys/**/*",
    ],
  },
};

export default nextConfig;
