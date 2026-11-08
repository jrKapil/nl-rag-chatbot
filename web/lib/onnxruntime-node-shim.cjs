// Shim: redirect onnxruntime-node to onnxruntime-web (WASM) for Vercel compatibility
// This file is used via Turbopack resolveAlias in next.config.ts
module.exports = require("onnxruntime-web")
