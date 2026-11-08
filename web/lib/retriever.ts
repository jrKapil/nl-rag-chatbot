/**
 * Retrieval for /api/ask (Phase 5).
 *
 * Query embedding via @huggingface/transformers + ONNX all-MiniLM-L6-v2
 * (same model family as fastembed ingestion — same vector space, guarded by
 * the Phase 7 drift-eval gate). Vector search via Pinecone REST against the
 * hosted `mf-faq` index (dim 384, cosine metric).
 *
 * Uses onnxruntime-web (via shim) instead of onnxruntime-node for Vercel
 * compatibility. The shim redirects onnxruntime-node → onnxruntime-web.
 *
 * Hit shape mirrors the Python side:
 *   {id, cosine, text, url, scheme, section, scraped_at}
 */

import { pipeline } from "@huggingface/transformers"

const EMB_MODEL = "Xenova/all-MiniLM-L6-v2" // ONNX-converted all-MiniLM-L6-v2 on HF Hub
const DIM = 384

let _embedder: Awaited<ReturnType<typeof pipeline>> | null = null

async function getEmbedder() {
  if (_embedder) return _embedder
  try {
    _embedder = await pipeline("feature-extraction", EMB_MODEL, {
      device: "cpu",
    })
  } catch (err) {
    _embedder = null
    throw err
  }
  return _embedder
}

function toFloats(tensor: any): number[] {
  const data = tensor.data ?? tensor.tolist?.() ?? tensor
  const flat: number[] = []
  if (Array.isArray(data)) {
    for (const row of data) {
      if (Array.isArray(row)) flat.push(...row)
      else flat.push(Number(row))
    }
  } else if (data && typeof data === "object" && Symbol.iterator in data) {
    for (const v of data) flat.push(Number(v))
  } else {
    flat.push(Number(data))
  }
  return flat
}

export async function embedQuery(text: string): Promise<number[]> {
  const model = await getEmbedder()
  const output = await (model as any)(text, {
    pooling: "mean",
    normalize: true,
  })
  const vec = toFloats(output)
  if (vec.length !== DIM) {
    throw new Error(`embedding dim mismatch: expected ${DIM}, got ${vec.length}`)
  }
  return vec
}

function env(key: string, fallback?: string): string {
  const v = (process.env as Record<string, string>)[key]
  if (!v && fallback === undefined) {
    throw new Error(`missing env var ${key}`)
  }
  return v ?? fallback!
}

const PINECONE_API_KEY = env("PINECONE_API_KEY")
const PINECONE_HOST = env("PINECONE_HOST")
const PINECONE_INDEX = env("PINECONE_INDEX", "mf-faq")
const API_VERSION = "2025-04"

function pineconeHeaders(): HeadersInit {
  return {
    "Api-Key": PINECONE_API_KEY,
    "X-Pinecone-API-Version": API_VERSION,
    "Content-Type": "application/json",
  }
}

export interface ChunkHit {
  id: string
  cosine: number
  text: string
  url: string
  scheme: string
  section: string
  scraped_at: string
}

export async function queryPinecone(
  vector: number[],
  topK: number,
): Promise<ChunkHit[]> {
  let res: Response
  try {
    res = await fetch(`https://${PINECONE_HOST}/query`, {
      method: "POST",
      headers: pineconeHeaders(),
      body: JSON.stringify({
        vector,
        topK,
        includeMetadata: true,
        namespace: "",
      }),
    })
  } catch (err) {
    throw new Error(`Pinecone fetch failed: ${err instanceof Error ? err.message : String(err)}`)
  }
  if (!res.ok) {
    throw new Error(`Pinecone query ${res.status}: ${await res.text()}`)
  }
  const json = (await res.json()) as any
  const matches = (json?.result?.matches ?? json?.matches ?? []) as any[]
  return matches.map((m) => {
    const md = m.metadata ?? {}
    return {
      id: m.id,
      cosine: Number(m.score ?? 0),
      text: md.text ?? "",
      url: md.url ?? "",
      scheme: md.scheme_name ?? "",
      section: md.section ?? "",
      scraped_at: md.scraped_at ?? "",
    }
  })
}

export async function retrieve(query: string, k: number): Promise<{
  hits: ChunkHit[]
  gatePassed: boolean
}> {
  const vec = await embedQuery(query)
  const hits = await queryPinecone(vec, k)
  const simThreshold = Number(env("SIM_THRESHOLD", "0.35"))
  const gatePassed = hits.length > 0 && hits[0].cosine >= simThreshold
  return { hits, gatePassed }
}
