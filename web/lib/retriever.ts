/**
 * Retrieval for /api/ask (Phase 5 — Vercel-compatible).
 *
 * Query embedding via HuggingFace Inference API (sentence-transformers/all-MiniLM-L6-v2).
 * Avoids native modules (onnxruntime-node) that fail on Vercel's Lambda runtime.
 * Vector search via Pinecone REST against the hosted `mf-faq` index.
 *
 * Hit shape mirrors the Python side:
 *   {id, cosine, text, url, scheme, section, scraped_at}
 */

const EMB_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
const DIM = 384
const HF_INFERENCE_URL = `https://router.huggingface.co/hf-inference/models/${EMB_MODEL}`

function env(key: string, fallback?: string): string {
  const v = (process.env as Record<string, string>)[key]
  if (!v && fallback === undefined) {
    throw new Error(`missing env var ${key}`)
  }
  return v ?? fallback!
}

export async function embedQuery(text: string): Promise<number[]> {
  const hfToken = (process.env as Record<string, string>).HF_TOKEN
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }
  if (hfToken) {
    headers["Authorization"] = `Bearer ${hfToken}`
  }

  // Retry up to 3 times (HF Inference cold-starts the model on first request)
  let lastError: Error | null = null
  for (let attempt = 0; attempt < 3; attempt++) {
    let res: Response
    try {
      res = await fetch(HF_INFERENCE_URL, {
        method: "POST",
        headers,
        body: JSON.stringify({ inputs: text }),
      })
    } catch (err) {
      lastError = new Error(`HF Inference fetch failed: ${err instanceof Error ? err.message : String(err)}`)
      await new Promise((r) => setTimeout(r, 2000))
      continue
    }
    if (res.status === 503) {
      // Model loading — wait and retry
      await new Promise((r) => setTimeout(r, 5000))
      continue
    }
    if (!res.ok) {
      const body = await res.text().catch(() => "")
      throw new Error(`HF Inference ${res.status}: ${body.slice(0, 300)}`)
    }
    const data = await res.json()
    // HF Inference returns [[...384 floats]] for a single input
    const vec: number[] = Array.isArray(data[0]) ? data[0] : data
    if (vec.length !== DIM) {
      throw new Error(`embedding dim mismatch: expected ${DIM}, got ${vec.length}`)
    }
    // normalize (HF returns unnormalized embeddings; fastembed normalizes)
    const norm = Math.sqrt(vec.reduce((s, v) => s + v * v, 0))
    return vec.map((v) => v / norm)
  }
  throw lastError ?? new Error("HF Inference: max retries exceeded")
}

function pineconeHeaders(): HeadersInit {
  return {
    "Api-Key": env("PINECONE_API_KEY"),
    "X-Pinecone-API-Version": "2025-04",
    "Content-Type": "application/json",
  }
}

const PINECONE_HOST = env("PINECONE_HOST")

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
