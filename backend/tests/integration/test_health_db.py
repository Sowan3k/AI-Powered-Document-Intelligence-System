from collections.abc import Iterator
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_storage
from app.core.config import Settings
from app.db.session import get_db
from app.main import create_app
from app.storage.local import LocalStorage


def test_health_reports_a_real_connected_database(engine: Engine, tmp_path: Path) -> None:
    app = create_app(Settings(_env_file=None))

    def _db() -> Iterator[Session]:
        session = sessionmaker(bind=engine)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path / "store")
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"
    assert response.json()["storage"] == "ok"
