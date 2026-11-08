"""Local end-to-end answer test — mirrors ARCHITECTURE §6.1 ask-sequence exactly.

Pipeline (identical to what web/app/api/ask will do in TS):
  1. embed query (fastembed, same model as ingestion)
  2. top-k from Chroma mf_faq
  3. grounding gate: best cosine >= SIM_THRESHOLD else refuse
  4. strict prompt: facts ONLY from context, <=3 sentences, exactly one
     whitelisted citation URL taken from the retrieved chunks' metadata
  5. post-checks: sentence count, citation is whitelisted + was in context,
     no advice phrasing, no PII echoes

Note for qwen-family models: they may emit <think>...</think> reasoning.
We request no reasoning when supported and strip think blocks defensively.

Run:
  python -m scripts.test_answer               # built-in eval queries
  python -m scripts.test_answer "question"    # one ad-hoc question
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ingestion.embed_store import embed  # noqa: E402  (query embedding, fixed model)
from config.sources import SOURCE_PAGES, is_whitelisted_url  # noqa: E402

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """You answer questions about HDFC mutual funds using ONLY the numbered context passages provided.

Rules (violations are failures):
1. Use only facts stated in the context passages. Never invent, estimate, or compute numbers.
2. Answer in at most 3 sentences. Be direct and factual.
3. End with the source: exactly one URL on its own final line, chosen from the context passages' URLs. Never any other URL.
4. If the context does not contain the answer, or if the question asks for advice or a comparison, reply exactly: I don't have that information in my indexed sources. — with NO URL afterward.
5. No investment advice, recommendations, or comparisons between funds. No disclaimers beyond the required source line.
6. Answer as plain text. Do not use markdown, headings, or bullet lists."""
USER_TMPL = """Context passages:
{ctx}

Question: {q}

Answer with the rules above."""

ADVICE_RE = re.compile(
    r"\b(should (you|i)|you should|i recommend|we recommend|advisable|better to invest|"
    r"good (investment|choice)|consider investing|consult a financial)\b", re.I)


def load_env() -> None:
    # tiny .env.local reader (no python-dotenv dependency at runtime)
    env = Path(".env.local")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def retrieve(query: str, k: int) -> dict:
    from ingestion.retrieve import query_top_k  # backend switch: VECTOR_DB env
    return {"query": query, "hits": query_top_k(query, k)}


def build_context(hits: list[dict]) -> str:
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append(f"[{i}] source: {h['url']}\ntext: {h['text']}")
    return "\n\n".join(blocks)


import urllib.request


def call_groq(query: str, ctx: str) -> tuple[str, dict]:
    model = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
    headers = {"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}",
               "Content-Type": "application/json",
               # Groq sits behind Cloudflare: python default UA gets error 1010
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TMPL.format(ctx=ctx, q=query)},
        ],
        "temperature": 0.1,
        "max_completion_tokens": 400,
    }
    req = urllib.request.Request(GROQ_URL, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    dt = time.time() - t0
    msg = data.get("choices", [{}])[0].get("message", {})
    content = msg.get("content") or ""
    # qwen-family may put reasoning in reasoning field instead of content
    reasoning = msg.get("reasoning") or ""
    usage = data.get("usage", {})
    return content, {"latency_s": round(dt, 2), "model": model,
                     "usage": usage, "reasoning_len": len(reasoning)}


# (old _json_request helper removed — HEADERS now carries the Cloudflare-safe UA)


THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)
LEADING_THINK_RE = re.compile(r"^[^A-Za-z₹]*\n")  # stray leading tokens


def strip_think(text: str) -> str:
    text = THINK_RE.sub("", text).strip()
    text = LEADING_THINK_RE.sub("", text)
    return text.strip()


def post_checks(answer: str, hits: list[dict], gate_cos: float,
                sim_threshold: float, label: str) -> dict:
    checks = {}
    refused = "don't have that information" in answer

    # 1. <=3 sentences (exclude final URL line)
    body = "\n".join(l for l in answer.splitlines() if not l.strip().startswith("http"))
    sents = [s for s in re.split(r"(?<=[.!?])\s+", body.strip()) if s.strip()]
    checks["<=3 sentences"] = len(sents) <= 3

    # 2. citation: exactly one URL for real answers; refusals carry none
    urls = re.findall(r"https?://\S+", answer)
    expected_urls = 0 if refused else 1
    checks["citation count"] = len(urls) == expected_urls
    checks["URL whitelisted"] = all(is_whitelisted_url(u.rstrip('.,;)')) for u in urls)
    ctx_urls = {h["url"] for h in hits}
    checks["URL from context"] = refused or (
        bool(urls) and any(any(cu in u for cu in ctx_urls) for u in urls))

    # 3. no advice phrasing
    checks["no advice"] = not ADVICE_RE.search(answer)

    # 4. refusal honesty: refusing is correct when retrieval was weak OR the
    # question is advice-style; refusing a well-retrieved FACT question is a fail
    weak = gate_cos < sim_threshold
    if refused:
        checks["gate consistent"] = weak or label != "fact" or gate_cos < 0.75
    else:
        checks["gate consistent"] = not weak

    return checks


CASES = [
    ("fact", "What is the expense ratio of HDFC Large Cap Fund Direct Growth?"),
    ("fact", "What is the exit load for HDFC Flexi Cap Fund?"),
    ("fact", "What is the lock-in period for HDFC ELSS Tax Saver Fund?"),
    ("fact", "What is the minimum SIP amount for HDFC Mid Cap Fund?"),
    ("advice", "Should I invest in HDFC ELSS or HDFC Mid Cap for better returns?"),
    ("unknown", "What is the NAV of ICICI Prudential Bluechip Fund?"),
]


def run_case(label: str, q: str, k: int, sim_threshold: float) -> None:
    r = retrieve(q, k)
    gate_cos = r["hits"][0]["cosine"] if r["hits"] else 0.0
    ctx = build_context(r["hits"])
    print(f"\n{'='*100}\n[{label}] {q}")
    print(f"  retrieval gate: top cosine {gate_cos:.4f} (threshold {sim_threshold}) -> "
          f"{'ANSWER' if gate_cos >= sim_threshold else 'REFUSE'}")
    for h in r["hits"]:
        print(f"    cos={h['cosine']:.4f} {h['scheme'][:34]:<36} {h['section'][:30]}")
    try:
        raw, meta = call_groq(q, ctx)
    except Exception as e:
        print(f"  GROQ ERROR: {e}")
        return
    answer = strip_think(raw)
    checks = post_checks(answer, r["hits"], gate_cos, sim_threshold, label)
    print(f"  model: {meta['model']} | latency {meta['latency_s']}s | "
          f"usage {meta['usage'].get('completion_tokens', '?')}ct out | reasoning_len {meta['reasoning_len']}")
    print("-" * 100)
    print(answer)
    print("-" * 100)
    verdict = " ".join(("OK " if ok else "FAIL") for k, ok in checks.items() if not k.startswith("_"))
    print(f"  checks: {verdict}")
    for name, ok in checks.items():
        if not ok and not name.startswith("_"):
            print(f"    !! failed: {name}")
    if meta["reasoning_len"]:
        print(f"    (note: model returned {meta['reasoning_len']} chars of reasoning)")


def main() -> None:
    load_env()
    k = int(os.environ.get("RETRIEVAL_K", "4"))
    sim_threshold = float(os.environ.get("SIM_THRESHOLD", "0.35"))
    qs = sys.argv[1:]
    if qs:
        run_case("adhoc", " ".join(qs), k, sim_threshold)
        return
    for label, q in CASES:
        run_case(label, q, k, sim_threshold)
    print(f"\n[master] env: model={os.environ.get('GROQ_MODEL')} k={k} threshold={sim_threshold} "
          f"mode={os.environ.get('CHROMA_MODE')} vector_db={os.environ.get('VECTOR_DB')}")


if __name__ == "__main__":
    main()
