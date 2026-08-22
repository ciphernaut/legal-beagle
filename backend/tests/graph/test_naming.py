from src.graph.naming import short_name


def test_short_name_strips_year():
    assert short_name("Corporations Act 2001") == "Corporations Act"
    assert short_name("Fair Work Act 2009 (Cth)") == "Fair Work Act"
    assert short_name("Commonwealth of Australia Constitution Act") == (
        "Commonwealth of Australia Constitution Act"
    )
