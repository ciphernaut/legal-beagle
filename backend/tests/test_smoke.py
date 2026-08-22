from sqlalchemy import text


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_db_connects(db_session):
    assert db_session.execute(text("SELECT 1")).scalar() == 1


def test_client_binds_test_database(client):
    """create_app() rebinds the global SessionLocal; guard that it lands on the test DB."""
    from src.db import SessionLocal

    from tests.conftest import TEST_URL

    assert str(SessionLocal.kw["bind"].url).endswith(TEST_URL.rsplit("/", 1)[-1])
    assert SessionLocal().get_bind().url.render_as_string(hide_password=False) == TEST_URL
