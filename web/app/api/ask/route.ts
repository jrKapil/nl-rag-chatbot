import { NextResponse } from "next/server"
import type { AnswerType, AskEnvelope } from "@/lib/envelope"
import { retrieve, type ChunkHit } from "@/lib/retriever"
import { callGroq } from "@/lib/llm"
import { SYSTEM_RULES, notFound } from "@/lib/prompts"
import {
  runGuardrails,
  scrubPii,
  classifyIntent,
} from "@/lib/guardrails"

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

function capSentences(text: string): string {
  const parts = text.split(/(?:\. |\! |\? )/)
  return parts.slice(0, 3).join(". ").trim()
}

function stripStamp(text: string): string {
  return text.replace(/Last updated from sources:\s*\S+/g, "").trim()
}

function isAdviceIntent(q: string): boolean {
  return classifyIntent(q) === "advice"
}

function finalizeAnswer(
  raw: string,
  hits: ChunkHit[],
  gatePassed: boolean,
  question: string,
): { answer: string; source: string; updated: string; type: AnswerType } {
  const answerBody = stripThink(raw)
  const refused = answerBody.includes("don't have that information")

  if (refused) {
    const clean = answerBody
      .replace(/https?:\/\/\S+/g, "")
      .replace(/Last updated from sources:\s*\S+/g, "")
      .trim()
    return {
      answer: clean,
      source: "",
      updated: "",
      type: isAdviceIntent(question) ? "refusal_advice" : "not_found",
    }
  }

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

  if (!question) {
    return NextResponse.json(
      { error: "missing question" },
      { status: 400 },
    )
  }

  // 1. Guardrails — PII filter + intent classify (run first, no upstream calls)
  const piiResult = runGuardrails(question, "")
  if (piiResult.intent === "pii") {
    // eslint-disable-next-line no-console
    console.log("[api/ask] guardrail: refusal_pii")
    return NextResponse.json({
      answer: piiResult.response!,
      source: "",
      updated: "",
      type: "refusal_pii",
      chunks_used: 0,
    })
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
    console.error("[api/ask] retrieval error:", scrubPii(String(err)))
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

  const bestUrl = hits[0]?.url ?? ""

  // Intent classify (advice / returns) — runs before LLM, zero LLM calls
  const intentResult = runGuardrails(question, bestUrl)
  if (intentResult.intent === "advice" || intentResult.intent === "returns") {
    // eslint-disable-next-line no-console
    console.log(`[api/ask] guardrail: ${intentResult.intent}`)
    return NextResponse.json({
      answer: intentResult.response!,
      source: intentResult.intent === "returns" ? bestUrl : "",
      updated: "",
      type:
        intentResult.intent === "advice" ? "refusal_advice" : "returns_redirect",
      chunks_used: 0,
    })
  }

  // 4. grounding gate — no relevant chunk → honest not_found
  if (!gatePassed) {
    const fb = notFound(bestUrl)
    return NextResponse.json({
      answer: fb,
      source: bestUrl,
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
    console.error("[api/ask] groq error:", scrubPii(String(err)))
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
  const { answer, source, updated, type } = finalizeAnswer(
    raw,
    hits,
    gatePassed,
    question,
  )
  return NextResponse.json({
    answer,
    source,
    updated,
    type,
    chunks_used: hits.length,
  })
}