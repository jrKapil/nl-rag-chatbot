export type AnswerType =
  | "factual"
  | "refusal_advice"
  | "refusal_pii"
  | "returns_redirect"
  | "not_found"
  | "rate_limited"

export interface AskEnvelope {
  answer: string
  source: string
  updated: string
  type: AnswerType
  chunks_used: number
}
