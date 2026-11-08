/**
 * Guardrails for /api/ask (Phase 6 — FR6, FR7, FR8).
 *
 * Runs BEFORE any upstream call (Pinecone / Groq) in the request path.
 *   1. PII filter   → refusal_pii (nothing logged, nothing sent upstream)
 *   2. Intent classify → refusal_advice / returns_redirect (zero LLM calls)
 *   3. RAG path    → factual / not_found  (handled by the route handler)
 *
 * Every log write on the request path MUST pass through `scrubPii`.
 */

export type Intent = "factual" | "advice" | "returns" | "pii"

export interface GuardrailResult {
  intent: Intent
  response: string | null // non-null → short-circuit with this answer
}

export const EDUCATOR_LINK = "https://www.sebi.gov.in/investor-education.html"

const PII_PATTERNS: { name: string; re: RegExp }[] = [
  { name: "PAN", re: /\b[A-Z]{5}[0-9]{4}[A-Z]\b/ },
  { name: "Aadhaar", re: /\b\d{12}\b/ },
  { name: "email", re: /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/ },
  { name: "OTP", re: /\b\d{6}\b/ },
  { name: "account-number", re: /\b\d{13,19}\b/ },
]

export function detectPii(text: string): string | null {
  for (const { name, re } of PII_PATTERNS) {
    if (re.test(text)) return name
  }
  return null
}

export function scrubPii(text: string): string {
  let out = text
  for (const { re } of PII_PATTERNS) {
    out = out.replace(re, "[REDACTED]")
  }
  return out
}

const ADVICE_RE =
  /\b(should\s+(i|you)|you\s+should|i\s+recommend|we\s+recommend|advisable|better\s+to\s+invest|good\s+(investment|choice|time)|consider\s+investing|consult\s+a\s+financial|portfolio|buy|sell)\b/i
const RETURNS_RE =
  /\b(returns?|performance|how\s+much\s+(did|do|will)|gain|profit|cagr|annuali[sz]ed)\b/i

export function classifyIntent(text: string): Intent {
  const pii = detectPii(text)
  if (pii) return "pii"
  if (ADVICE_RE.test(text)) return "advice"
  if (RETURNS_RE.test(text)) return "returns"
  return "factual"
}

export function refusalPii(): string {
  return "I can't handle that. Please don't share PAN, Aadhaar, account numbers, OTPs, emails, or phone numbers — I don't store or process personal data. Ask me a factual question about the indexed HDFC schemes instead."
}

export function refusalAdvice(): string {
  return `I don't have that information in my indexed sources. This chatbot shares only factual scheme details from the indexed Groww pages — it does not give investment advice. For investor education, see SEBI: ${EDUCATOR_LINK}`
}

export function returnsRedirect(sourceUrl: string): string {
  return `I can't compute or compare returns. For performance details, see the official scheme factsheet: ${sourceUrl}`
}

export function notFound(sourceUrl: string): string {
  return `I don't have that information in my indexed sources. The answer may be on the official scheme page: ${sourceUrl}`
}

/**
 * Run all guardrails in the mandated order. Returns a non-null `response` only
 * when the request must short-circuit (PII / advice / returns). Otherwise
 * returns intent="factual" with response=null and the caller proceeds to RAG.
 */
export function runGuardrails(
  question: string,
  bestSourceUrl: string,
): GuardrailResult {
  const intent = classifyIntent(question)
  if (intent === "pii") {
    return { intent, response: refusalPii() }
  }
  if (intent === "advice") {
    return { intent, response: refusalAdvice() }
  }
  if (intent === "returns") {
    return { intent, response: returnsRedirect(bestSourceUrl) }
  }
  return { intent: "factual", response: null }
}
