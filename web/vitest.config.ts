import { defineConfig } from "vitest/config"
import path from "path"

export default defineConfig({
  test: {
    // Test files live at repo-root tests/ts/ (per IMPLEMENTATION.md layout)
    // and web/tests/ (co-located). Both resolve @/* to web/.
    include: ["../tests/ts/**/*.test.ts", "tests/**/*.test.ts"],
    environment: "node",
    globals: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname),
    },
  },
})
