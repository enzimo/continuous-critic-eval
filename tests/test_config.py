import pytest
from fastapi.testclient import TestClient

from critic_observer.app import create_app
from critic_observer.config import Settings


@pytest.mark.parametrize("source", ["environment", "file"])
def test_eight_character_credentials_start_and_authenticate(tmp_path, monkeypatch, source):
    monkeypatch.setenv("OBSERVER_DATABASE", str(tmp_path / "observer.sqlite3"))
    monkeypatch.setenv("OBSERVER_PUBLIC_URL", "http://testserver")
    for name, value in (
        ("OBSERVER_ADMIN_TOKEN", "operator"),
        ("OBSERVER_INGEST_TOKEN", "reporter"),
    ):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name + "_FILE", raising=False)
        if source == "file":
            path = tmp_path / name.lower()
            path.write_text(value + "\n")
            monkeypatch.setenv(name + "_FILE", str(path))
        else:
            monkeypatch.setenv(name, value)
    settings = Settings.from_env()
    assert settings.admin_token == "operator"
    assert settings.ingest_token == "reporter"
    with TestClient(create_app()) as client:
        assert client.post("/api/login", json={"token": "operator"}).status_code == 200
        assert client.get("/api/dashboard").status_code == 200
        client.cookies.clear()
        writer = {"Authorization": "Bearer reporter"}
        assert client.get("/api/critics", headers=writer).status_code == 200
        assert client.get("/api/dashboard", headers=writer).status_code == 403
        assert client.get("/api/dashboard").status_code == 401


def test_short_credentials_rejected_in_both_configuration_paths(tmp_path, monkeypatch):
    for name in ("OBSERVER_ADMIN_TOKEN", "OBSERVER_INGEST_TOKEN"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name + "_FILE", raising=False)
    for short_name in ("OBSERVER_ADMIN_TOKEN", "OBSERVER_INGEST_TOKEN"):
        other_name = (
            "OBSERVER_INGEST_TOKEN"
            if short_name == "OBSERVER_ADMIN_TOKEN"
            else "OBSERVER_ADMIN_TOKEN"
        )
        monkeypatch.setenv(other_name, "abcdefgh")
        monkeypatch.setenv(short_name, "1234567")
        with pytest.raises(ValueError, match=f"{short_name} needs at least 8 characters"):
            Settings.from_env()
        monkeypatch.delenv(short_name)
        path = tmp_path / short_name.lower()
        path.write_text("1234567\n")
        monkeypatch.setenv(short_name + "_FILE", str(path))
        with pytest.raises(ValueError, match=f"{short_name} needs at least 8 characters"):
            Settings.from_env()
        monkeypatch.delenv(short_name + "_FILE")
    for admin, ingest in (("1234567", "abcdefgh"), ("abcdefgh", "1234567")):
        with pytest.raises(ValueError, match="Both credentials must contain at least 8 characters"):
            Settings(tmp_path / "unused.sqlite3", admin, ingest)
    with pytest.raises(ValueError, match="must differ"):
        Settings(tmp_path / "unused.sqlite3", "abcdefgh", "abcdefgh")
