import { NextResponse } from "next/server"
import type { AnswerType, AskEnvelope } from "@/lib/envelope"
import { retrieve, type ChunkHit } from "@/lib/retriever"
import { callGroq } from "@/lib/llm"
import { SYSTEM_RULES, notFound } from "@/lib/prompts"

// Minimal PII filter (runs before any upstream call). Phase 6 formalizes this
// into web/lib/guardrails.ts with unit tests; this keeps FR7 safe today.
const PII_PATTERNS = [
  /\b[A-Z]{5}[0-9]{4}[A-Z]\b/,          // PAN
  /\b\d{12}\b/,                          // Aadhaar
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/, // email
  /\b\d{13,19}\b/,                       // account-like numbers
]

function hasPii(text: string): boolean {
  return PII_PATTERNS.some((re) => re.test(text))
}

// Simple intent classifier for type assignment when the model refuses.
// Advice questions that pass the gate → refusal_advice; out-of-scope
// questions that pass the gate but have no relevant facts → not_found.
const ADVICE_PATTERNS = [
  /\bshould\s+(i|you)\b/,
  /\byou\s+should\b/,
  /\b(i|we)\s+recommend\b/,
  /\badvisable\b/,
  /\bbetter\s+to\s+invest\b/,
  /\bgood\s+(investment|choice|time)\b/,
  /\bconsider\s+investing\b/,
  /\bconsult\s+a\s+financial\b/,
]

function isAdviceQuestion(q: string): boolean {
  return ADVICE_PATTERNS.some((re) => re.test(q.toLowerCase()))
}

function stripStamp(text: string): string {
  return text.replace(/Last updated from sources:\s*\S+/g, "").trim()
}

const RETRIEVAL_K = Number(process.env.RETRIEVAL_K ?? "4")

function buildContext(hits: ChunkHit[]): string {
  return hits
    .map(
      (h, i) =>
        `[${i + 1}] source: ${h.url} (scraped_at: ${h.scraped_at})\ntext: ${h.text}`,
    )
    .join("\n\n")
}

function userPrompt(ctx: string, q: string): string {
  return `Context passages:\n${ctx}\n\nQuestion: ${q}\n\nAnswer with the rules above.`
}

function stripThink(text: string): string {
  return text
    .replace(/<\|start_header_id\|>[\s\S]*?<\|end_header_id\|>/g, "")
    .replace(/<\|eot_id\|>/g, "")
    .replace(/<\|begin_of_thought\|>[\s\S]*?<\|end_of_thought\|>/g, "")
    .replace(/\[\s*思考\s*\]?\s*\n?/gi, "")
    .replace(/\b(?:思考|thinking|reasoning)\s*[:：].*/g, "")
    .trim()
}

// Cap the answer at 3 sentences (defense in depth — the prompt already asks
// for ≤3 sentences; this guarantees it).
function capSentences(text: string): string {
  const parts = text.split(/(?:\. |\! |\? )/)
  return parts.slice(0, 3).join(". ").trim()
}

function finalizeAnswer(
  raw: string,
  hits: ChunkHit[],
  gatePassed: boolean,
  question: string,
): { answer: string; source: string; updated: string; type: AnswerType } {
  const answerBody = stripThink(raw)
  const refused = answerBody.includes("don't have that information")

  // refusals carry no URL and no stamp
  if (refused) {
    const clean = answerBody
      .replace(/https?:\/\/\S+/g, "")
      .replace(/Last updated from sources:\s*\S+/g, "")
      .trim()
    return {
      answer: clean,
      source: "",
      updated: "",
      type: isAdviceQuestion(question) ? "refusal_advice" : "not_found",
    }
  }

  // factual: body text only (≤3 sentences); citation lives in envelope fields
  const source = hits[0]?.url ?? ""
  const updated = hits[0]?.scraped_at?.slice(0, 10) ?? ""
  const body = capSentences(
    stripStamp(answerBody.replace(/https?:\/\/\S+/g, "").trim()),
  )
  return { answer: body, source, updated, type: "factual" }
}

export async function POST(req: Request): Promise<NextResponse> {
  let question = ""
  try {
    const body = (await req.json()) as { question?: string }
    question = String(body.question ?? "").trim()
  } catch {
    // malformed body
  }

  // 1. PII filter — runs first, nothing sent upstream
  if (question && hasPii(question)) {
    return NextResponse.json({
      answer: REFUSAL_PII_PLACEHOLDER(),
      source: "",
      updated: "",
      type: "refusal_pii",
      chunks_used: 0,
    })
  }

  if (!question) {
    return NextResponse.json(
      { error: "missing question" },
      { status: 400 },
    )
  }

  // 2-3. Embed + retrieve from Pinecone, then grounding gate
  let hits: ChunkHit[] = []
  let gatePassed = false
  try {
    const result = await retrieve(question, RETRIEVAL_K)
    hits = result.hits
    gatePassed = result.gatePassed
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error("[api/ask] retrieval error:", err)
    return NextResponse.json(
      {
        answer: "I'm unable to search my indexed sources right now. Please try again shortly.",
        source: "",
        updated: "",
        type: "not_found",
        chunks_used: 0,
      },
      { status: 500 },
    )
  }

  // 4. grounding gate — no relevant chunk → honest not_found
  if (!gatePassed) {
    const fb = notFound(hits[0]?.url ?? "")
    return NextResponse.json({
      answer: fb,
      source: hits[0]?.url ?? "",
      updated: hits[0]?.scraped_at?.slice(0, 10) ?? "",
      type: "not_found",
      chunks_used: hits.length,
    })
  }

  // 5. Generation — grounded prompt → Groq
  let raw = ""
  try {
    const ctx = buildContext(hits)
    raw = await callGroq(
      [
        { role: "system", content: SYSTEM_RULES },
        { role: "user", content: userPrompt(ctx, question) },
      ],
      { temperature: 0.1, maxTokens: 400 },
    )
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error("[api/ask] groq error:", err)
    const isRateLimited = err instanceof Error && err.message.includes("429")
    return NextResponse.json(
      {
        answer: isRateLimited
          ? "I'm rate-limited by the generation service. Please try again in a moment."
          : "I'm unable to generate an answer right now. Please try again shortly.",
        source: "",
        updated: "",
        type: isRateLimited ? "rate_limited" : "not_found",
        chunks_used: hits.length,
      },
      { status: isRateLimited ? 429 : 500 },
    )
  }

  // 6. Post-checks → final envelope
  const { answer, source, updated, type } = finalizeAnswer(raw, hits, gatePassed, question)
  return NextResponse.json({
    answer,
    source,
    updated,
    type,
    chunks_used: hits.length,
  })
}

function REFUSAL_PII_PLACEHOLDER(): string {
  return "I can't handle that. Please don't share PAN, Aadhaar, account numbers, OTPs, emails, or phone numbers — I don't store or process personal data. Ask me a factual question about the indexed HDFC schemes instead."
}
