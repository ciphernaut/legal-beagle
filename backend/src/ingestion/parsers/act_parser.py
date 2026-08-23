from __future__ import annotations

import re
from dataclasses import dataclass, field

# The 2001+ consolidated legislation.gov.au style has no period after the number ("51  Heading");
# the original enacted-Act style (e.g. the Constitution as originally transcribed) has one
# ("51.  Heading."), and its head-of-power items use "(xx.)" rather than "(xx)". Both are real
# formats seen in the Federal Register of Legislation corpus, so both are matched; the trailing
# period is not captured, so identifiers come out clean either way.
SECTION_RE = re.compile(r"^(\d+[A-Z]{0,3})\.?\s{2,}(\S.*)$")
CHILD_RE = re.compile(r"^\s*\(([a-z0-9]{1,4}|[ivxlc]{1,6})\.?\)\s+(.*)$")


@dataclass
class ParsedProvision:
    identifier: str
    heading: str | None
    text: str
    children: list[ParsedProvision] = field(default_factory=list)


def _finish(prov: ParsedProvision | None, lines: list[str]) -> None:
    if prov is not None:
        prov.text = "\n".join(lines).strip()


def parse_act(text: str) -> list[ParsedProvision]:
    out: list[ParsedProvision] = []
    current = ParsedProvision("preamble", None, "")
    cur_lines: list[str] = []
    child: ParsedProvision | None = None
    child_lines: list[str] = []

    def close_child() -> None:
        nonlocal child, child_lines
        _finish(child, child_lines)
        child, child_lines = None, []

    for raw in text.splitlines():
        m = SECTION_RE.match(raw)
        if m:
            close_child()
            _finish(current, cur_lines)
            out.append(current)
            current = ParsedProvision(f"s{m.group(1)}", m.group(2).strip(), "")
            cur_lines = []
            continue
        cm = CHILD_RE.match(raw) if current.identifier != "preamble" else None
        if cm:
            close_child()
            child = ParsedProvision(f"{current.identifier}({cm.group(1)})", None, "")
            child_lines = [cm.group(2)]
            current.children.append(child)
            continue
        if child is not None:
            child_lines.append(raw)
        else:
            cur_lines.append(raw)

    close_child()
    _finish(current, cur_lines)
    out.append(current)
    return out
