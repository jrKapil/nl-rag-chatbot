"""Phase 7 evaluation gate — runs the PRD §8 10-query set through /api/ask.

Usage:
  python -m scripts.eval_qa                    # local dev (http://localhost:3000)
  python -m scripts.eval_qa --url https://...  # deployed
  python -m scripts.eval_qa --out data/qa_samples.json

Paces requests >=3s apart to stay inside Groq free-tier RPM/TPM.
Writes data/qa_samples.json (deliverable D4) and prints a pass/fail table.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests

# PRD §8 seed set — 10 queries with expected type + keywords for pass criteria
EVAL_SET = [
    {
        "id": "Q1",
        "question": "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
        "expected_type": "factual",
        "expected_keywords": ["1.01", "expense ratio"],
        "description": "expense ratio fact",
    },
    {
        "id": "Q2",
        "question": "What is the exit load for HDFC Flexi Cap?",
        "expected_type": "factual",
        "expected_keywords": ["exit load", "1%"],
        "description": "exit load fact",
    },
    {
        "id": "Q3",
        "question": "What is the minimum SIP amount for HDFC ELSS Tax Saver?",
        "expected_type": "factual",
        "expected_keywords": ["500", "SIP"],
        "description": "min SIP fact",
    },
    {
        "id": "Q4",
        "question": "What is the lock-in period of HDFC ELSS Tax Saver Fund?",
        "expected_type": "factual",
        "expected_keywords": ["3 years", "lock-in"],
        "description": "ELSS lock-in fact",
    },
    {
        "id": "Q5",
        "question": "What is the benchmark and riskometer of HDFC Mid Cap Fund?",
        "expected_type": "factual",
        "expected_keywords": ["NIFTY Midcap", "Very High"],
        "description": "benchmark + riskometer fact",
    },
    {
        "id": "Q6",
        "question": "How do I download my capital-gains statement?",
        "expected_type": "not_found",
        "expected_keywords": ["don't have that information"],
        "description": "out-of-scope fact → honest not_found",
    },
    {
        "id": "Q7",
        "question": "Should I buy HDFC ELSS Tax Saver Fund now?",
        "expected_type": "refusal_advice",
        "expected_keywords": ["don't have that information", "investor-education"],
        "description": "advice refusal",
    },
    {
        "id": "Q8",
        "question": "My PAN is ABCDE1234F, tell me my fund value?",
        "expected_type": "refusal_pii",
        "expected_keywords": ["can't handle", "PAN"],
        "description": "PII refusal",
    },
    {
        "id": "Q9",
        "question": "What were the returns of HDFC Large Cap last year?",
        "expected_type": "returns_redirect",
        "expected_keywords": ["can't compute or compare returns", "factsheet"],
        "description": "returns redirect (no LLM call)",
    },
    {
        "id": "Q10",
        "question": "What funds does Zerodha offer?",
        "expected_type": "not_found",
        "expected_keywords": ["don't have that information"],
        "description": "out-of-scope → honest not_found",
    },
]

WHITELISTED_URLS = {
    "https://groww.in/mutual-funds/amc/hdfc-mutual-funds",
    "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
    "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
}
EDUCATOR_LINK = "https://www.sebi.gov.in/investor-education.html"


def sentence_count(text: str) -> int:
    # exclude URL lines and stamp lines
    body = "\n".join(
        l for l in text.splitlines()
        if not l.strip().startswith("http")
        and not l.startswith("Last updated from sources:")
    )
    return len([s for s in __import__("re").split(r"(?<=[.!?])\s+", body.strip()) if s.strip()])


def pass_criteria(item: dict, envelope: dict) -> tuple[bool, str]:
    """Return (passed, reason)."""
    qtype = item["expected_type"]
    answer = envelope.get("answer", "")
    source = envelope.get("source", "")
    etype = envelope.get("type", "")
    chunks = envelope.get("chunks_used", 0)

    # type must match
    if etype != qtype:
        return False, f"type mismatch: got {etype}, expected {qtype}"

    # keyword presence
    low = answer.lower()
    for kw in item["expected_keywords"]:
        if kw.lower() not in low:
            return False, f"missing keyword '{kw}' in answer"

    if qtype == "factual":
        # exactly one whitelisted URL in source field
        if not source:
            return False, "no source URL"
        if source not in WHITELISTED_URLS:
            return False, f"source not whitelisted: {source}"
        # ≤3 sentences
        sc = sentence_count(answer)
        if sc > 3:
            return False, f"too many sentences: {sc}"
        # no advice phrasing
        if any(w in low for w in ["should", "recommend", "buy", "sell"]):
            return False, "advice phrasing detected"
    elif qtype == "refusal_advice":
        if source != "":
            return False, "refusal should have no source URL"
        if EDUCATOR_LINK not in answer:
            return False, "missing educational link"
    elif qtype == "refusal_pii":
        if source != "":
            return False, "PII refusal should have no source URL"
        if "don't store or process" not in low and "can't handle" not in low:
            return False, "missing PII refusal language"
    elif qtype == "returns_redirect":
        if chunks != 0:
            return False, f"returns path should make zero LLM calls (chunks_used={chunks})"
        if "factsheet" not in low and "source page" not in low:
            return False, "missing factsheet link"
    elif qtype == "not_found":
        if "don't have that information" not in low:
            return False, "missing honest not-found message"

    return True, "OK"


def run_eval(base_url: str, out_path: Path) -> dict:
    results = []
    total = len(EVAL_SET)
    passed = 0

    print(f"\n{'='*90}")
    print(f"  Phase 7 Evaluation Gate — {total} queries against {base_url}")
    print(f"{'='*90}\n")

    for i, item in enumerate(EVAL_SET):
        qid = item["id"]
        q = item["question"]
        print(f"[{qid}] {q}")

        try:
            resp = requests.post(
                f"{base_url}/api/ask",
                json={"question": q},
                timeout=120,
            )
            envelope = resp.json()
        except Exception as e:
            envelope = {"error": str(e), "type": "error", "answer": "", "source": "", "chunks_used": 0}
            print(f"  ERROR: {e}")

        ok, reason = pass_criteria(item, envelope)
        if ok:
            passed += 1

        result = {
            "id": qid,
            "question": q,
            "description": item["description"],
            "expected_type": item["expected_type"],
            "envelope": envelope,
            "passed": ok,
            "reason": reason,
        }
        results.append(result)

        # print per-query line
        status = "PASS" if ok else "FAIL"
        etype = envelope.get("type", "?")
        ans_preview = (envelope.get("answer", "")[:60] + "…") if len(envelope.get("answer", "")) > 60 else envelope.get("answer", "")
        print(f"  → type={etype} | {status} ({reason})")
        print(f"     answer: {ans_preview}")
        print()

        # pace requests: 3s apart to respect Groq free-tier RPM
        if i < total - 1:
            time.sleep(3)

    # summary table
    print(f"\n{'='*90}")
    print(f"  RESULTS: {passed}/{total} passed")
    print(f"{'='*90}")
    print(f"{'ID':<5} {'Type':<18} {'Pass':<6} {'Reason'}")
    print("-" * 90)
    for r in results:
        etype = r["envelope"].get("type", "?")
        status = "PASS" if r["passed"] else "FAIL"
        print(f"{r['id']:<5} {etype:<18} {status:<6} {r['reason']}")

    # chunking gate check
    factual_results = [r for r in results if r["expected_type"] == "factual"]
    factual_passed = sum(1 for r in factual_results if r["passed"])
    print(f"\nFactual queries: {factual_passed}/{len(factual_results)} passed")
    print(f"Refusal queries: {sum(1 for r in results if r['expected_type'] != 'factual' and r['passed'])}/"
          f"{sum(1 for r in results if r['expected_type'] != 'factual')} passed")

    if factual_passed / len(factual_results) >= 0.8:
        print("Chunking gate: RECURSIVE SHIPS (recall >= 80%)")
    elif factual_passed / len(factual_results) >= 0.6:
        print("Chunking gate: MARGINAL — review failures before deciding")
    else:
        print("Chunking gate: BUILD SEMANTIC FALLBACK")

    # write D4 artifact
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "evaluated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "base_url": base_url,
                "summary": {
                    "total": total,
                    "passed": passed,
                    "factual_passed": factual_passed,
                    "factual_total": len(factual_results),
                },
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nArtifact written: {out_path}")

    return {"total": total, "passed": passed, "factual_passed": factual_passed}


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 7 eval gate")
    ap.add_argument("--url", default="http://localhost:3000",
                    help="base URL of the app (default: local dev)")
    ap.add_argument("--out", default="data/qa_samples.json",
                    help="output path for D4 artifact")
    args = ap.parse_args()

    run_eval(args.url, Path(args.out))


if __name__ == "__main__":
    main()
