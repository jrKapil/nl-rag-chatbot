import { beforeAll, describe, expect, it } from "vitest"

// retriever.ts reads these at import time; placeholder values are never used
// because this test only exercises the local query embedder.
beforeAll(() => {
  process.env.PINECONE_API_KEY ??= "test-key"
  process.env.PINECONE_HOST ??= "test.example.invalid"
})

describe("query embedding (in-process ONNX, no HF Inference API)", () => {
  it("returns a normalised 384-dimension vector loaded in Node", async () => {
    const { embedQuery } = await import("../../web/lib/retriever")
    const vec = await embedQuery("What is the expense ratio of HDFC Large Cap Fund?")
    expect(vec).toHaveLength(384)
    const norm = Math.sqrt(vec.reduce((sum, v) => sum + v * v, 0))
    expect(norm).toBeCloseTo(1, 3)
    expect(vec.every((v) => Number.isFinite(v))).toBe(true)
  }, 180_000)
})
