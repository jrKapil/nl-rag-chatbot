import { Metadata } from "next"
import Chat from "@/app/components/Chat"
import styles from "./page.module.css"

export const metadata: Metadata = {
  title: "HDFC Mutual Fund FAQ — Facts-Only Chatbot",
  description:
    "Ask factual questions about HDFC Mutual Fund schemes. Answers are grounded in indexed Groww pages with a cited source link.",
}

// Blocking prerender: we read searchParams to pre-fill the input from example links.
export const instant = false

const EXAMPLES = [
  "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
  "What is the exit load for HDFC Flexi Cap?",
  "What is the lock-in period of HDFC ELSS Tax Saver Fund?",
]

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
  const sp = await searchParams
  const initialQ =
    typeof sp.q === "string" ? sp.q : Array.isArray(sp.q) ? sp.q[0] : undefined

  return (
    <main className={styles.page}>
      <h1 className={styles.welcome}>
        Ask factual questions about HDFC Mutual Fund schemes.
      </h1>
      <p className={styles.intro}>
        Answers come from 5 indexed Groww pages — HDFC Mutual Fund overview plus
        Large Cap, Flexi Cap, ELSS Tax Saver, and Mid Cap funds. Every factual
        answer carries one cited source link.
      </p>
      <div className={styles.disclaimer}>
        <strong>Facts-only. No investment advice.</strong>
      </div>
      <div className={styles.examples}>
        <span className={styles.examplesLabel}>Try:</span>
        {EXAMPLES.map((q) => (
          <a
            key={q}
            href={`?q=${encodeURIComponent(q)}`}
            className={styles.exampleChip}
          >
            {q}
          </a>
        ))}
      </div>
      <Chat initialQuestion={initialQ} />
    </main>
  )
}
