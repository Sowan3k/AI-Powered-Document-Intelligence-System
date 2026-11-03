from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text

from app.db.models import Base
from tests.integration.conftest import run_alembic
from tests.unit.test_models import EXPECTED_TABLES


def test_upgrade_creates_every_table_and_the_vector_extension(engine: Engine) -> None:
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        has_vector = conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
    assert tables >= EXPECTED_TABLES
    assert has_vector == 1


def test_models_match_the_migrated_schema(engine: Engine) -> None:
    with engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(context, Base.metadata)
    ignored = {"alembic_version"}
    diff = [d for d in diff if not (d[0] == "remove_table" and d[1].name in ignored)]
    assert diff == []


def test_check_constraint_names_match_the_models(engine: Engine) -> None:
    with engine.connect() as conn:
        db_names = set(
            conn.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE contype = 'c' AND connamespace = 'public'::regnamespace"
                )
            ).scalars()
        )
        conn.execute(text("DROP SCHEMA IF EXISTS model_check CASCADE"))
        conn.execute(text("CREATE SCHEMA model_check"))
        conn.execute(text("SET search_path TO model_check, public"))
        Base.metadata.create_all(conn, checkfirst=False)
        model_names = set(
            conn.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE contype = 'c' AND connamespace = 'model_check'::regnamespace"
                )
            ).scalars()
        )
        conn.rollback()
    assert db_names == model_names


def test_downgrade_then_upgrade_again(engine: Engine) -> None:
    run_alembic(engine, "downgrade", "base")
    with engine.connect() as conn:
        assert not (EXPECTED_TABLES & set(inspect(conn).get_table_names()))
    run_alembic(engine, "upgrade", "head")
    with engine.connect() as conn:
        assert set(inspect(conn).get_table_names()) >= EXPECTED_TABLES
