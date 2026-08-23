from pathlib import Path

from src.ingestion.parsers.act_parser import parse_act

FIXTURE = Path(__file__).parent.parent / "fixtures" / "act_sample.txt"
ENACTED_FIXTURE = Path(__file__).parent.parent / "fixtures" / "act_sample_enacted.txt"


def test_parses_sections_and_subsections():
    secs = parse_act(FIXTURE.read_text())
    assert [s.identifier for s in secs] == ["preamble", "s51", "s52", "s109"]
    s51 = secs[1]
    assert s51.heading == "Legislative powers of the Parliament"
    assert s51.text.startswith("The Parliament shall, subject to this Constitution")
    assert [c.identifier for c in s51.children] == ["s51(i)", "s51(ii)", "s51(xx)"]
    assert s51.children[2].text.startswith("foreign corporations")
    assert secs[3].text.startswith("When a law of a State")


def test_no_sections_returns_preamble_only():
    secs = parse_act("Just some text with no sections.")
    assert [s.identifier for s in secs] == ["preamble"]


def test_parses_original_enacted_style_with_periods():
    """The Constitution as originally transcribed (and some other older Acts) numbers sections
    as "51.  Heading." and head-of-power items as "(xx.)" rather than the 2001+ consolidated
    "51  Heading" / "(xx)" style. Both must parse to the same clean identifiers."""
    secs = parse_act(ENACTED_FIXTURE.read_text())
    assert [s.identifier for s in secs] == ["preamble", "s51", "s109"]
    s51 = secs[1]
    assert s51.heading == "Legislative powers of the Parliament."
    assert [c.identifier for c in s51.children] == ["s51(i)", "s51(ii)", "s51(xx)"]
    assert s51.children[2].text.startswith("foreign corporations")
    assert secs[2].text.startswith("When a law of a State")
