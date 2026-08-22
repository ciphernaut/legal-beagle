from src.ingestion.parsers.citation_parser import parse_citations


def test_neutral_citation():
    c = parse_citations("See Mabo v Queensland (No 2) [1992] HCA 23 at [5].")
    assert len(c.neutral) == 1
    assert (c.neutral[0].year, c.neutral[0].court, c.neutral[0].number) == (1992, "HCA", 23)
    assert c.neutral[0].raw == "[1992] HCA 23"


def test_reported_citation():
    c = parse_citations("(1992) 175 CLR 1 and (2006) 229 CLR 1")
    assert [(r.volume, r.series, r.page) for r in c.reported] == [(175, "CLR", 1), (229, "CLR", 1)]


def test_section_refs_with_and_without_act_hint():
    c = parse_citations(
        "Under s 51(xx) of the Constitution, and ss 9 and 12 of the Corporations Act 2001 (Cth), and section 109."
    )
    secs = [(s.section, s.act_hint) for s in c.sections]
    assert ("51(xx)", "Constitution") in secs
    assert ("9", "Corporations Act 2001") in secs
    assert ("12", "Corporations Act 2001") in secs
    assert ("109", None) in secs
    assert any(s.raw == "s 51(xx) of the Constitution" for s in c.sections)


def test_dedupe_preserves_order():
    c = parse_citations("[2020] HCA 1 ... [2019] HCA 2 ... [2020] HCA 1")
    assert [n.raw for n in c.neutral] == ["[2020] HCA 1", "[2019] HCA 2"]
