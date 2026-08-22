from sqlalchemy import text


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_db_connects(db_session):
    assert db_session.execute(text("SELECT 1")).scalar() == 1
