from __future__ import annotations

import re
from dataclasses import dataclass, field

NEUTRAL_RE = re.compile(r"\[(\d{4})\]\s+([A-Z][A-Za-z]{1,9})\s+(\d+)")
REPORTED_RE = re.compile(
    r"\((\d{4})\)\s+(\d+)\s+(CLR|ALR|ALJR|FCR|FLR|NSWLR|VR|Qd R|SASR|WAR|Tas R)\s+(\d+)"
)

# "s 51(xx)", "ss 9 and 12", "section 109" — captures a list of section ids.
SECTION_LIST_RE = re.compile(
    r"\b(?:ss?\.?|sections?)\s+"
    r"(\d+[A-Z]{0,3}(?:\([^)\s]{1,6}\))*"
    r"(?:(?:,\s*|\s+and\s+)\d+[A-Z]{0,3}(?:\([^)\s]{1,6}\))*)*)"
)
# "of the Corporations Act 2001 (Cth)" or "of the Constitution" right after a section list
ACT_HINT_RE = re.compile(r"^\s*of\s+the\s+((?:[A-Z][\w''\-]*\s+)*(?:Act\s+\d{4}|Constitution))")
SECTION_SPLIT_RE = re.compile(r",\s*|\s+and\s+")


@dataclass(frozen=True)
class NeutralCitation:
    year: int
    court: str
    number: int
    raw: str


@dataclass(frozen=True)
class ReportedCitation:
    year: int
    volume: int
    series: str
    page: int
    raw: str


@dataclass(frozen=True)
class SectionRef:
    section: str
    act_hint: str | None
    raw: str


@dataclass
class Citations:
    neutral: list[NeutralCitation] = field(default_factory=list)
    reported: list[ReportedCitation] = field(default_factory=list)
    sections: list[SectionRef] = field(default_factory=list)


def _dedupe(items):
    seen, out = set(), []
    for it in items:
        if it.raw not in seen:
            seen.add(it.raw)
            out.append(it)
    return out


def parse_citations(text: str) -> Citations:
    neutral = [
        NeutralCitation(int(m.group(1)), m.group(2), int(m.group(3)), m.group(0))
        for m in NEUTRAL_RE.finditer(text)
    ]
    reported = [
        ReportedCitation(int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4)), m.group(0))
        for m in REPORTED_RE.finditer(text)
    ]
    sections: list[SectionRef] = []
    for m in SECTION_LIST_RE.finditer(text):
        hint_m = ACT_HINT_RE.match(text[m.end():])
        hint = hint_m.group(1).strip() if hint_m else None
        for sec in SECTION_SPLIT_RE.split(m.group(1)):
            sec = sec.strip()
            if sec:
                raw = f"s {sec}" + (f" of the {hint}" if hint else "")
                sections.append(SectionRef(sec, hint, raw))
    return Citations(_dedupe(neutral), _dedupe(reported), _dedupe(sections))
