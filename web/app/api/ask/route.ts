import { NextResponse } from "next/server"
import type { AskEnvelope } from "@/lib/envelope"

// Fixed envelope — Phase 4 stub. Phase 5 replaces this with the real
// retrieve → ground → generate → post-check pipeline.
const STUB: AskEnvelope = {
  answer:
    "This is a stubbed response. The retrieval + generation pipeline is wired in Phase 5.",
  source: "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
  updated: "2026-11-08",
  type: "factual",
  chunks_used: 4,
}

export async function POST(req: Request): Promise<NextResponse> {
  let question = ""
  try {
    const body = (await req.json()) as { question?: string }
    question = String(body.question ?? "")
  } catch {
    // malformed body — still return the fixed stub envelope
  }
  // eslint-disable-next-line no-console
  console.log("[api/ask stub] question:", question)
  return NextResponse.json(STUB)
}
