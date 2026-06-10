"""Bilingual message catalog.

All user-facing strings live in ``backend/locales/{en,ar}.json``. Error responses
always carry BOTH languages, so the catalog is the single source of truth and the
API never depends on an Accept-Language header for correctness.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

LOCALES_DIR = Path(__file__).resolve().parents[2] / "locales"
SUPPORTED_LOCALES = ("en", "ar")


@lru_cache
def _catalog(locale: str) -> dict[str, Any]:
    path = LOCALES_DIR / f"{locale}.json"
    with path.open(encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def t(key: str, locale: str, **params: Any) -> str | None:
    """Resolve a dotted key (e.g. ``errors.auth.invalid_credentials.message``).

    Returns None when the key is missing — callers decide the fallback. Messages
    may contain ``{placeholders}`` filled from ``params``.
    """
    node: Any = _catalog(locale)
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    if not isinstance(node, str):
        return None
    return node.format(**params) if params else node
