from pathlib import Path

from src.ingestion.parsers.judgment_parser import parse_judgment, split_case_citation

FIXTURE = Path(__file__).parent.parent / "fixtures" / "judgment_sample.txt"


def test_paragraphs_and_judges():
    j = parse_judgment(FIXTURE.read_text())
    assert j.judges == "MASON CJ, BRENNAN, DEANE, DAWSON, TOOHEY, GAUDRON AND McHUGH JJ"
    assert [n for n, _ in j.paragraphs] == [1, 2, 3]
    assert j.paragraphs[0][1] == (
        "The plaintiffs claim native title over the Murray Islands.\nSecond line of paragraph one."
    )
    assert j.paragraphs[2][1] == "The doctrine of terra nullius is rejected."


def test_split_case_citation():
    assert split_case_citation("Mabo v Queensland (No 2) [1992] HCA 23") == (
        "Mabo v Queensland (No 2)", "[1992] HCA 23")
    assert split_case_citation("Unknown v Unknown") == ("Unknown v Unknown", None)
