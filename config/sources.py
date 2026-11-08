"""Source whitelist — the single source of truth for every URL in the system.

Rule (cross-cutting #1, IMPLEMENTATION.md): the ONLY URLs ever fetched,
validated, cited, or rendered are those listed here, plus the designated
educator/factsheet links in guardrail templates (ARCHITECTURE §6.1.2).

Data scope per PRD §4: exactly 5 Groww pages — 1 AMC overview + 4 HDFC
schemes. No crawling of internal links. Do not add URLs casually.
"""

from dataclasses import dataclass


ALLOWED_URL_PREFIX = "https://groww.in/mutual-funds/"


@dataclass(frozen=True)
class SourcePage:
    slug: str           # local file name for data/raw/{slug}.html|.txt
    name: str           # display name (used in Chroma metadata + D2)
    page_type: str      # amc | scheme
    url: str            # the absolute whitelisted URL


SOURCE_PAGES: tuple[SourcePage, ...] = (
    SourcePage(
        slug="amc-hdfc-mutual-funds",
        name="HDFC Mutual Fund (AMC overview)",
        page_type="amc",
        url="https://groww.in/mutual-funds/amc/hdfc-mutual-funds",
    ),
    SourcePage(
        slug="hdfc-large-cap-fund-direct-growth",
        name="HDFC Large Cap Fund Direct Growth",
        page_type="scheme",
        url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    ),
    SourcePage(
        # Groww serves the Flexi Cap scheme under the "equity fund" URL slug.
        slug="hdfc-equity-fund-direct-growth",
        name="HDFC Flexi Cap Fund Direct Plan Growth",
        page_type="scheme",
        url="https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
    ),
    SourcePage(
        slug="hdfc-elss-tax-saver-fund-direct-plan-growth",
        name="HDFC ELSS Tax Saver Fund Direct Plan Growth",
        page_type="scheme",
        url="https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
    ),
    SourcePage(
        slug="hdfc-mid-cap-fund-direct-growth",
        name="HDFC Mid Cap Fund Direct Growth",
        page_type="scheme",
        url="https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
    ),
)


SUPPORTED_TYPES = {"factual", "refusal_advice", "refusal_pii",
                   "returns_redirect", "not_found", "rate_limited"}


def get_page_by_slug(slug: str) -> SourcePage | None:
    return next((p for p in SOURCE_PAGES if p.slug == slug), None)


def is_whitelisted_url(url: str) -> bool:
    """A URL is citable only if it is exactly one of the 5 whitelisted URLs.

    Downstream usage (web/lib post-checks mirrors this rule in TypeScript):
    every answer's `source` must pass this check. Prefix-matching is NOT
    sufficient — only exact membership in SOURCE_PAGES counts.
    """
    return any(url.strip() == p.url for p in SOURCE_PAGES)


def scheme_urls() -> tuple[SourcePage, ...]:
    return tuple(p for p in SOURCE_PAGES if p.page_type == "scheme")


def amc_pages() -> tuple[SourcePage, ...]:
    return tuple(p for p in SOURCE_PAGES if p.page_type == "amc")


# Sanity check on import: whitelist must always contain exactly 5 pages,
# 1 AMC + 4 schemes, per PRD §4.
assert len(SOURCE_PAGES) == 5, "Whitelist must contain exactly 5 pages (PRD §4)"
assert len(amc_pages()) == 1, "Exactly one AMC overview page expected"
assert len(scheme_urls()) == 4, "Exactly four scheme pages expected"
assert len({p.url for p in SOURCE_PAGES}) == 5, "URLs must be unique"
