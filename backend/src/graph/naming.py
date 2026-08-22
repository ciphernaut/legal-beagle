"""Canonical naming helpers for graph nodes.

Lives in ``src.graph`` because both ``src.graph`` and ``src.ingestion`` need it;
putting it in the ingestion source loader made the graph layer depend on ingestion.
"""

from __future__ import annotations

import re

_SHORT_NAME_RE = re.compile(r"\s+(Act|Regulations?)\s+\d{4}.*$")


def short_name(title: str) -> str:
    """"Corporations Act 2001 (Cth)" -> "Corporations Act"."""
    return _SHORT_NAME_RE.sub(r" \1", title).strip()
