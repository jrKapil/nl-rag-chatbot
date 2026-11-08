"""Shared .env.local loader (no python-dotenv dependency).

Only sets vars that are missing — shell-real values win (12-factor style).
"""

from __future__ import annotations

import os
from pathlib import Path


def load_env(path: str = ".env.local") -> None:
    env = Path(path)
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
