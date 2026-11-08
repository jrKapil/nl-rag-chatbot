import { describe, it, expect } from "vitest"
import {
  classifyIntent,
  detectPii,
  scrubPii,
  runGuardrails,
  refusalPii,
  refusalAdvice,
  returnsRedirect,
  notFound,
} from "../../web/lib/guardrails"

describe("guardrails (Phase 6)", () => {
  // ---- PII detection (FR7) ----
  describe("detectPii", () => {
    it("detects PAN", () => {
      expect(detectPii("My PAN is ABCDE1234F")).toBe("PAN")
    })
    it("detects Aadhaar (12 digits)", () => {
      expect(detectPii("Aadhaar 123456789012")).toBe("Aadhaar")
    })
    it("detects email", () => {
      expect(detectPii("email me at user@example.com")).toBe("email")
    })
    it("detects 6-digit OTP", () => {
      expect(detectPii("OTP 123456")).toBe("OTP")
    })
    it("detects 13-19 digit account number", () => {
      expect(detectPii("account 1234567890123")).toBe("account-number")
    })
    it("returns null for clean factual question", () => {
      expect(detectPii("What is the expense ratio of HDFC Large Cap?")).toBeNull()
    })
    it("returns null for empty string", () => {
      expect(detectPii("")).toBeNull()
    })
  })

  // ---- Intent classification ----
  describe("classifyIntent", () => {
    it("PII question → pii", () => {
      expect(classifyIntent("My PAN is ABCDE1234F")).toBe("pii")
    })
    it("advice question → advice", () => {
      expect(classifyIntent("Should I buy HDFC ELSS Tax Saver Fund now?")).toBe("advice")
    })
    it("returns question → returns", () => {
      expect(classifyIntent("What were the returns of HDFC Large Cap last year?")).toBe("returns")
    })
    it("factual question → factual", () => {
      expect(classifyIntent("What is the expense ratio of HDFC Large Cap Fund?")).toBe("factual")
    })
  })

  // ---- scrubPii ----
  describe("scrubPii", () => {
    it("redacts PAN", () => {
      expect(scrubPii("PAN ABCDE1234F")).toBe("PAN [REDACTED]")
    })
    it("redacts email", () => {
      expect(scrubPii("email user@example.com")).toBe("email [REDACTED]")
    })
    it("leaves clean text unchanged", () => {
      expect(scrubPii("expense ratio")).toBe("expense ratio")
    })
  })

  // ---- runGuardrails (table-driven, PRD §8 refusal classes) ----
  describe("runGuardrails — refusal classes", () => {
    const cases: { q: string; expectedIntent: string; expectResponse: boolean }[] = [
      { q: "Should I buy HDFC ELSS Tax Saver Fund now?", expectedIntent: "advice", expectResponse: true },
      { q: "My PAN is ABCDE1234F, tell me my fund value?", expectedIntent: "pii", expectResponse: true },
      { q: "What were the returns of HDFC Large Cap last year?", expectedIntent: "returns", expectResponse: true },
      { q: "What is the expense ratio of HDFC Large Cap Fund Direct Growth?", expectedIntent: "factual", expectResponse: false },
    ]
    for (const c of cases) {
      it(`${c.expectedIntent}: "${c.q.slice(0, 40)}..."`, () => {
        const result = runGuardrails(c.q, "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth")
        expect(result.intent).toBe(c.expectedIntent)
        if (c.expectResponse) {
          expect(result.response).not.toBeNull()
          expect(result.response!.length).toBeGreaterThan(0)
        } else {
          expect(result.response).toBeNull()
        }
      })
    }
  })

  // ---- refusal messages ----
  describe("refusal messages", () => {
    it("refusalPii mentions no storage", () => {
      const msg = refusalPii()
      expect(msg).toContain("don't store or process")
      expect(msg).toContain("PAN")
    })
    it("refusalAdvice includes educational link", () => {
      const msg = refusalAdvice()
      expect(msg).toContain("investor-education.html")
      expect(msg).toContain("don't have that information")
    })
    it("returnsRedirect includes source URL", () => {
      const url = "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
      const msg = returnsRedirect(url)
      expect(msg).toContain(url)
      expect(msg).toContain("can't compute or compare returns")
    })
    it("notFound includes source URL", () => {
      const url = "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
      const msg = notFound(url)
      expect(msg).toContain(url)
      expect(msg).toContain("don't have that information")
    })
  })

  // ---- adversarial variants ----
  describe("adversarial variants", () => {
    it("adversarial: buy with PAN", () => {
      const result = runGuardrails("buy PAN ABCDE1234F", "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth")
      // PII takes priority (runs first)
      expect(result.intent).toBe("pii")
    })
    it("adversarial: min SIP question (factual)", () => {
      const result = runGuardrails("min SIP?", "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth")
      expect(result.intent).toBe("factual")
    })
    it("adversarial: returns last week", () => {
      const result = runGuardrails("what were good returns last week?", "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth")
      // "good returns" matches ADVICE_RE first (good returns), so advice
      // or returns — either is a refusal, which is correct
      expect(["advice", "returns"]).toContain(result.intent)
    })
  })
})
