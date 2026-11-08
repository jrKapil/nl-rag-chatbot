"use client"

import { useEffect, useState } from "react"
import styles from "./chat.module.css"
import type { AskEnvelope } from "@/lib/envelope"

interface ChatProps {
  initialQuestion?: string
}

export default function Chat({ initialQuestion }: ChatProps) {
  const [question, setQuestion] = useState(initialQuestion ?? "")
  const [answer, setAnswer] = useState<AskEnvelope | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Example links navigate with ?q=...; the server re-renders and passes the
  // question down as a prop. Re-pick it up on every prop change.
  useEffect(() => {
    setQuestion(initialQuestion ?? "")
  }, [initialQuestion])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const q = question.trim()
    if (!q) return
    setError(null)
    setLoading(true)
    setAnswer(null)
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      })
      if (!res.ok) throw new Error(`server responded ${res.status}`)
      const envelope = (await res.json()) as AskEnvelope
      setAnswer(envelope)
    } catch (err) {
      setError(err instanceof Error ? err.message : "request failed")
    } finally {
      setLoading(false)
    }
  }

  const badgeLabel = (t: string) =>
    t.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())

  return (
    <section className={styles.chat}>
      <form onSubmit={handleSubmit} className={styles.form}>
        <label htmlFor="question-input" className={styles.label}>
          Ask a factual question about HDFC Mutual Fund schemes
        </label>
        <div className={styles.inputGroup}>
          <input
            id="question-input"
            name="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. What is the expense ratio of HDFC Large Cap Fund Direct Growth?"
            disabled={loading}
            autoComplete="off"
            spellCheck={false}
          />
          <button
            type="submit"
            disabled={loading || !question.trim()}
            className={styles.button}
          >
            Ask
          </button>
        </div>
        {error && <p className={styles.error}>{error}</p>}
      </form>

      {answer && (
        <section className={styles.answer}>
          <h2 className={styles.answerTitle}>Answer</h2>
          <p className={styles.answerText}>{answer.answer}</p>
          <div className={styles.meta}>
            <span className={styles.badge} data-type={answer.type}>
              {badgeLabel(answer.type)}
            </span>
            {answer.updated && (
              <span className={styles.updated}>
                Last updated from sources: {answer.updated}
              </span>
            )}
          </div>
          {answer.source && (
            <p className={styles.source}>
              Source:{" "}
              <a href={answer.source} target="_blank" rel="noopener noreferrer">
                {answer.source}
              </a>
            </p>
          )}
        </section>
      )}
    </section>
  )
}
