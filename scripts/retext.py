"""No-network text rebuild + re-embed utility.

python -m scripts.retext   # rebuild .txt/.sections.json from stored HTML, then ingest
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.scrape import rebuild_texts  # noqa: E402
from scripts.ingest import run as ingest_run  # noqa: E402


def main() -> None:
    rebuild_texts()
    ingest_run(scrape_first=False)


if __name__ == "__main__":
    main()
