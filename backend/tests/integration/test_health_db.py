from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.session import get_db
from app.main import create_app


def test_health_reports_a_real_connected_database(engine: Engine) -> None:
    app = create_app(Settings(_env_file=None))

    def _db() -> Iterator[Session]:
        session = sessionmaker(bind=engine)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _db
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"
