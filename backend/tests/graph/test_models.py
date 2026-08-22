from datetime import date

from src.graph.models import (
    Act,
    ActVersion,
    Case,
    Court,
    Edge,
    EdgeKind,
    Extraction,
    Judgment,
    Jurisdiction,
    NodeType,
    Paragraph,
    Provision,
)


def test_round_trip_act_case_edge(db_session):
    cth = Jurisdiction(code="CTH", name="Commonwealth", level="Commonwealth")
    hca = Court(code="HCA", name="High Court of Australia", jurisdiction=cth, tier=1)
    act = Act(title="Corporations Act 2001", short_name="Corporations Act", year=2001,
              jurisdiction=cth, status="in_force", source_url="https://example/act",
              source_licence="CC-BY-4.0", extraction=Extraction.parsed)
    ver = ActVersion(act=act, version_id="C2004A00818", in_force_from=date(2001, 7, 15),
                     source_url="https://example/act/v1")
    s1 = Provision(act_version=ver, identifier="s1", heading="Short title", text="This Act…",
                   source_url="https://example/act/v1", source_licence="CC-BY-4.0",
                   extraction=Extraction.parsed)
    case = Case(name="Example v Example", neutral_citation="[2020] HCA 1", court=hca,
                decided_on=date(2020, 1, 1), source_url="https://example/case",
                source_licence="Crown", extraction=Extraction.parsed)
    j = Judgment(case=case, judges="Kiefel CJ", disposition="majority")
    p = Paragraph(judgment=j, number=1, text="Para one.")
    db_session.add_all([cth, hca, act, ver, s1, case, j, p])
    db_session.flush()

    e = Edge(src_type=NodeType.case, src_id=case.id, dst_type=NodeType.provision,
             dst_id=s1.id, kind=EdgeKind.INTERPRETS, extraction=Extraction.parsed,
             confidence=1.0, source_url="https://example/case",
             source_licence="Crown", note="applied in obiter")
    db_session.add(e)
    db_session.commit()

    got = db_session.get(Edge, e.id)
    assert got.kind == EdgeKind.INTERPRETS
    assert got.src_id == case.id
    assert (got.source_url, got.source_licence, got.note) == (
        "https://example/case", "Crown", "applied in obiter")
    prov = db_session.get(Provision, s1.id)
    assert prov.act_version.act.short_name == "Corporations Act"
    assert (prov.source_url, prov.source_licence, prov.extraction) == (
        "https://example/act/v1", "CC-BY-4.0", Extraction.parsed)
