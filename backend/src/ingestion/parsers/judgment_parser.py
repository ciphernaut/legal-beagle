from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.ingestion.parsers.citation_parser import NEUTRAL_RE

PARA_RE = re.compile(r"^\s*(?:\[(\d{1,4})\]|(\d{1,4})[.\]]?)\s+(\S.*)$")
JUDGES_RE = re.compile(r"\b(CJ|JJ|J)\b")


@dataclass
class ParsedJudgment:
    judges: str | None
    paragraphs: list[tuple[int, str]] = field(default_factory=list)


def parse_judgment(text: str) -> ParsedJudgment:
    judges: str | None = None
    paras: list[tuple[int, list[str]]] = []
    for raw in text.splitlines():
        m = PARA_RE.match(raw)
        if m:
            num = int(m.group(1) or m.group(2))
            paras.append((num, [m.group(3)]))
            continue
        if paras:
            paras[-1][1].append(raw)
        elif judges is None and JUDGES_RE.search(raw):
            judges = raw.strip()
    return ParsedJudgment(
        judges=judges,
        paragraphs=[(n, "\n".join(lines).strip()) for n, lines in paras],
    )


def split_case_citation(citation: str) -> tuple[str, str | None]:
    m = NEUTRAL_RE.search(citation)
    if not m:
        return citation.strip(), None
    return citation[: m.start()].strip(), m.group(0)
