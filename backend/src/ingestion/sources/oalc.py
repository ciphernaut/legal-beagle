from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.graph.models import (
    Act,
    ActVersion,
    Case,
    Edge,
    EdgeKind,
    Extraction,
    Judgment,
    Jurisdiction,
    NodeType,
    Paragraph,
    Provision,
)
from src.graph.naming import short_name
from src.graph.seed import get_court_by_code
from src.ingestion.parsers.act_parser import ParsedProvision, parse_act
from src.ingestion.parsers.judgment_parser import parse_judgment, split_case_citation

OALC_JURISDICTION_MAP = {
    "commonwealth": "CTH", "new_south_wales": "NSW", "victoria": "VIC", "queensland": "QLD",
    "south_australia": "SA", "western_australia": "WA", "tasmania": "TAS",
    "australian_capital_territory": "ACT", "northern_territory": "NT",
}
LICENCE_BY_SOURCE = {
    "federal_register_of_legislation": "CC-BY-4.0",
    "high_court_of_australia": "Crown-HCA",
}
YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")


@dataclass
class LoadStats:
    acts: int = 0
    cases: int = 0
    skipped: int = 0


__all__ = ["LoadStats", "load_oalc", "short_name"]  # short_name re-exported from graph.naming


def _parse_date(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s[:10]) if s else None
    except ValueError:
        return None


def _add_provisions(session: Session, version: ActVersion, provs: list[ParsedProvision],
                    parent: Provision | None = None) -> None:
    # Provenance comes from the version (URL) and the act (licence) it was parsed out of.
    for p in provs:
        row = Provision(act_version=version, identifier=p.identifier, heading=p.heading,
                        text=p.text, parent=parent, source_url=version.source_url,
                        source_licence=version.act.source_licence,
                        extraction=Extraction.parsed)
        session.add(row)
        session.flush()
        _add_provisions(session, version, p.children, row)


def _load_act(session: Session, rec: dict, juris: Jurisdiction) -> bool:
    if session.scalar(select(ActVersion).where(ActVersion.version_id == rec["version_id"])):
        return False
    title = rec["citation"].strip()
    act = session.scalar(select(Act).where(Act.title == title, Act.jurisdiction_id == juris.id))
    if act is None:
        ym = YEAR_RE.search(title)
        act = Act(title=title, short_name=short_name(title), year=int(ym.group(1)) if ym else None,
                  jurisdiction_id=juris.id, status="in_force", source_url=rec["url"],
                  source_licence=LICENCE_BY_SOURCE.get(rec["source"]),
                  extraction=Extraction.parsed)
        session.add(act)
        session.flush()
        session.add(Edge(src_type=NodeType.act, src_id=act.id, dst_type=NodeType.jurisdiction,
                         dst_id=juris.id, kind=EdgeKind.IN_JURISDICTION,
                         extraction=Extraction.parsed, confidence=1.0,
                         source_url=act.source_url, source_licence=act.source_licence))
    version = ActVersion(act=act, version_id=rec["version_id"],
                         in_force_from=_parse_date(rec.get("date")), source_url=rec["url"])
    session.add(version)
    session.flush()
    _add_provisions(session, version, parse_act(rec["text"]))
    return True


def _load_case(session: Session, rec: dict) -> str:
    """Returns 'loaded', 'exists' or 'skipped'."""
    name, neutral = split_case_citation(rec["citation"])
    if neutral is None:
        return "skipped"
    neutral = " ".join(neutral.split())
    court = get_court_by_code(session, neutral.split()[1])
    if court is None:
        return "skipped"
    if session.scalar(select(Case).where(Case.neutral_citation == neutral)):
        return "exists"
    parsed = parse_judgment(rec["text"])
    case = Case(name=name, neutral_citation=neutral, court_id=court.id,
                decided_on=_parse_date(rec.get("date")), source_url=rec["url"],
                source_licence=LICENCE_BY_SOURCE.get(rec["source"]), extraction=Extraction.parsed)
    session.add(case)
    session.flush()
    session.add(Edge(src_type=NodeType.case, src_id=case.id, dst_type=NodeType.court,
                     dst_id=court.id, kind=EdgeKind.DECIDED_BY, extraction=Extraction.parsed,
                     confidence=1.0, source_url=case.source_url,
                     source_licence=case.source_licence))
    j = Judgment(case=case, judges=parsed.judges, disposition="majority")
    session.add(j)
    session.flush()
    session.add_all([Paragraph(judgment=j, number=n, text=t) for n, t in parsed.paragraphs])
    session.flush()
    return "loaded"


def load_oalc(session: Session, path: Path, *, sources: set[str],
              jurisdictions: set[str]) -> LoadStats:
    stats = LoadStats()
    juris_rows = {j.code: j for j in session.scalars(select(Jurisdiction)).all()}
    with path.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("source") not in sources or rec.get("jurisdiction") not in jurisdictions:
                stats.skipped += 1
                continue
            juris = juris_rows[OALC_JURISDICTION_MAP[rec["jurisdiction"]]]
            if rec["type"] == "primary_legislation":
                stats.acts += int(_load_act(session, rec, juris))
            elif rec["type"] == "decision":
                outcome = _load_case(session, rec)
                stats.cases += outcome == "loaded"
                stats.skipped += outcome == "skipped"
            else:
                stats.skipped += 1
    return stats
