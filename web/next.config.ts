import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // Keep native/external modules out of the Turbopack bundle so they resolve
  // from node_modules at runtime (required for onnxruntime-node on Vercel).
  serverExternalPackages: ["@huggingface/transformers", "onnxruntime-node"],
  // Ensure the ONNX runtime native bindings are traced into the function bundle.
  outputFileTracingIncludes: {
    "/api/ask": ["./node_modules/onnxruntime-node/**/*"],
  },
};

export default nextConfig;
