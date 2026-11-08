"""Interactive CLI tester for the local RAG pipeline (Pinecone-backed).

Type questions one after another; `quit`/`exit`/`q` to leave.

Run:
  .\.venv\Scripts\python.exe -m scripts.ask

Env: .env.local (PINECONE_API_KEY, GROQ_API_KEY, GROQ_MODEL,
VECTOR_DB, RETRIEVAL_K, SIM_THRESHOLD)"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ingestion.envload import load_env  # noqa: E402
from ingestion.retrieve import query_top_k  # noqa: E402  (backend switch: VECTOR_DB)
from config.sources import is_whitelisted_url  # noqa: E402

load_env()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """You answer questions about HDFC mutual funds using ONLY the numbered context passages provided.

Rules (violations are failures):
1. Use only facts stated in the context passages. Never invent, estimate, or compute numbers.
2. Answer in at most 3 sentences. Be direct and factual.
3. End with exactly one source URL on its own final line, chosen from the context passages' URLs. Never any other URL.
4. On the line immediately after the source URL, add the source freshness stamp: Last updated from sources: YYYY-MM-DD — using the scraped_at date of the cited source passage shown in context.
5. If the context does not contain the answer, or if the question asks for advice or a comparison, reply exactly: I don't have that information in my indexed sources. — with NO URL and no stamp afterward.
6. No investment advice, recommendations, or comparisons between funds. No disclaimers beyond the required source line.
7. Answer as plain text. Do not use markdown, headings, or bullet lists."""

USER_TMPL = """Context passages:
{ctx}

Question: {q}

Answer with the rules above."""

REASON_RE = re.compile(r"\b(?:思考|thinking|reasoning)\s*[:：].*", re.S)


def call_groq(query: str, ctx: str) -> tuple[str, dict]:
    model = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TMPL.format(ctx=ctx, q=query)},
        ],
        "temperature": 0.1,
        "max_completion_tokens": 400,
    }
    headers = {"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}",
               "Content-Type": "application/json",
               # Groq sits behind Cloudflare: python default UA gets error 1010
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    req = urllib.request.Request(GROQ_URL, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    dt = round(time.time() - t0, 2)
    msg = data.get("choices", [{}])[0].get("message", {})
    content = msg.get("content") or ""
    return content.strip(), {"latency_s": dt,
                             "model": model,
                             "usage": data.get("usage", {})}


def strip_think(text: str) -> str:
    text = re.sub(r"<\|start_header_id\|>.*?<\|end_header_id\|>", "", text, flags=re.S)
    text = re.sub(r"<\|eot_id\|>", "", text, flags=re.S)
    text = re.sub(r"<\|begin_of_thought\|>.*?<\|end_of_thought\|>", "", text, flags=re.S)
    text = re.sub(r"\[\s*思考\s*\]?\s*\n?", "", text, flags=re.I | re.S)
    text = REASON_RE.sub("", text)
    return text.strip()


def last_updated_line(hits: list[dict]) -> str:
    """Deterministic source freshness stamp from the top hit's scraped_at."""
    ts = hits[0]["scraped_at"] if hits else ""
    date = ts[:10] if ts else ""
    return f"Last updated from sources: {date}" if date else ""


def build_context(hits: list[dict]) -> str:
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append(f"[{i}] source: {h['url']} (scraped_at: {h['scraped_at']})\ntext: {h['text']}")
    return "\n\n".join(blocks)


def main() -> None:
    k = int(os.environ.get("RETRIEVAL_K", "4"))
    sim_threshold = float(os.environ.get("SIM_THRESHOLD", "0.35"))
    model = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
    backend = os.environ.get("VECTOR_DB", "chroma")
    print(f"== Interactive RAG tester ==")
    print(f"model: {model} | vector backend: {backend} | top-k: {k} | "
          f"threshold: {sim_threshold}")
    print('Type your question and press Enter. Type "quit" to exit.\n')

    while True:
        try:
            q = input("Question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            return
        if not q:
            continue
        if q.lower() in {"quit", "exit", "q", ":q"}:
            print("bye")
            return

        try:
            hits = query_top_k(q, k)
        except Exception as e:
            print(f"retrieval error: {e}\n")
            continue

        gate_cos = hits[0]["cosine"] if hits else 0.0
        ctx = build_context(hits)
        try:
            raw, meta = call_groq(q, ctx)
        except Exception as e:
            print(f"groq error: {e}\n")
            continue

        answer = strip_think(raw)
        refused = "don't have that information" in answer
        stamp = last_updated_line(hits)
        if stamp and not refused and not any(l.startswith("Last updated from sources:") for l in answer.splitlines()):
            answer = answer.rstrip() + "\n" + stamp
        print()
        print(answer)
        print()
        print(f"  (latency {meta['latency_s']}s | top chunk cos={gate_cos:.4f} "
              f"gate={'ANSWER' if gate_cos >= sim_threshold else 'REFUSE'} | "
              f"sources: " + "; ".join(h["url"].rsplit("/", 1)[-1] for h in hits[:3]) + ")\n")


if __name__ == "__main__":
    main()
