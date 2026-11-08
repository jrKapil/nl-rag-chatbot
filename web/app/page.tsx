import { Metadata } from "next"
import Chat from "@/app/components/Chat"
import styles from "./page.module.css"

export const metadata: Metadata = {
  title: "HDFC Mutual Fund FAQ — Facts-Only Chatbot",
  description:
    "Ask factual questions about HDFC Mutual Fund schemes. Answers are grounded in indexed Groww pages with a cited source link.",
}

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
    <div className={styles.shell}>
      <div className={styles.container}>
        <header className={styles.header}>
          <h1 className={styles.title}>HDFC Mutual Fund FAQ</h1>
          <p className={styles.subtitle}>
            Ask factual questions about HDFC Mutual Fund schemes. Answers are
            grounded in 5 indexed Groww pages and carry one cited source link.
          </p>
        </header>

        <div className={styles.disclaimer}>
          <span className={styles.disclaimerIcon}>ℹ️</span>
          <strong>Facts-only. No investment advice.</strong>
          <span style={{ marginLeft: 6, fontWeight: 400 }}>
            This assistant does not recommend buys or sells, compare returns, or
            handle personal data.
          </span>
        </div>

        <div className={styles.examples}>
          <span className={styles.examplesLabel}>Try:</span>
          <div className={styles.chips}>
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
        </div>

        <div className={styles.card}>
          <div className={styles.cardTitle}>Chat</div>
          <Chat initialQuestion={initialQ} />
        </div>

        <footer className={styles.footer}>
          Knowledge frozen at scrape time · 5 whitelisted Groww pages ·
          Embeddings: MiniLM-L6-v2 · Vector store: Pinecone
        </footer>
      </div>
    </div>
  )
}
