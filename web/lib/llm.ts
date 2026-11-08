/**
 * LLM client for /api/ask (Phase 5).
 *
 * OpenAI-compatible Groq endpoint. Handles 429 rate limits with one
 * `retry-after` honouring retry, then a curated `rate_limited` fallback.
 */

const GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

function env(key: string, fallback?: string): string {
  const v = (process.env as Record<string, string>)[key]
  if (!v && fallback === undefined) {
    throw new Error(`missing env var ${key}`)
  }
  return v ?? fallback!
}

const GROQ_API_KEY = env("GROQ_API_KEY")
const GROQ_MODEL = env("GROQ_MODEL", "qwen/qwen3.8-27b")

export interface GroqMessage {
  role: "system" | "user" | "assistant"
  content: string
}

export class GroqRateLimitedError extends Error {
  retryAfter?: number
  constructor(message: string, retryAfter?: number) {
    super(message)
    this.name = "GroqRateLimitedError"
    this.retryAfter = retryAfter
  }
}

export async function callGroq(
  messages: GroqMessage[],
  opts?: { temperature?: number; maxTokens?: number },
): Promise<string> {
  const temperature = opts?.temperature ?? 0.1
  const maxTokens = opts?.maxTokens ?? 400

  const attempt = async (retry: boolean): Promise<string> => {
    const res = await fetch(GROQ_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${GROQ_API_KEY}`,
        "Content-Type": "application/json",
        // Groq sits behind Cloudflare: node/undici default UA can get 403/1010
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
      },
      body: JSON.stringify({
        model: GROQ_MODEL,
        messages,
        temperature,
        max_completion_tokens: maxTokens,
      }),
    })

    if (res.status === 429 && retry) {
      const retryAfter = res.headers.get("retry-after")
      const ms = retryAfter ? parseInt(retryAfter, 10) * 1000 : 2000
      // eslint-disable-next-line no-console
      console.log(`[groq] 429 rate limited, retrying after ${ms}ms`)
      await new Promise((r) => setTimeout(r, ms))
      return attempt(false)
    }

    if (!res.ok) {
      const body = await res.text().catch(() => "")
      throw new Error(`Groq ${res.status}: ${body.slice(0, 300)}`)
    }

    const json = await res.json()
    return (json.choices?.[0]?.message?.content ?? "").trim()
  }

  return attempt(true)
}
