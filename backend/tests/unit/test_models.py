"""Static checks on the SQLAlchemy models. No database needed."""

from sqlalchemy import Float, Numeric
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db.models import EMBED_DIM, Base

EXPECTED_TABLES = {
    "documents",
    "pages",
    "sheets",
    "invoices",
    "line_items",
    "validation_issues",
    "corrections",
    "jobs",
    "processing_events",
    "reconciliations",
}

MONEY_COLUMNS = {
    ("invoices", "subtotal"),
    ("invoices", "tax"),
    ("invoices", "total"),
    ("line_items", "amount"),
}


def test_every_table_in_the_data_model_exists() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_money_is_numeric_14_2_never_float() -> None:
    for table_name, column_name in MONEY_COLUMNS:
        column_type = Base.metadata.tables[table_name].c[column_name].type
        assert isinstance(column_type, Numeric)
        assert not isinstance(column_type, Float)
        assert (column_type.precision, column_type.scale) == (14, 2)


def test_unit_price_and_quantity_keep_four_decimals() -> None:
    items = Base.metadata.tables["line_items"]
    for name in ("quantity", "unit_price"):
        assert (items.c[name].type.precision, items.c[name].type.scale) == (14, 4)


def test_embedding_dimension_comes_from_config() -> None:
    assert Base.metadata.tables["invoices"].c["embedding"].type.dim == EMBED_DIM


def test_status_columns_have_check_constraints() -> None:
    ddl = str(CreateTable(Base.metadata.tables["jobs"]).compile(dialect=postgresql.dialect()))
    assert (
        "CONSTRAINT ck_jobs_status CHECK (status IN ('queued', 'running', 'succeeded', 'failed'))"
        in ddl
    )


def test_child_rows_cascade_when_parent_is_deleted() -> None:
    for table_name in ("pages", "sheets", "invoices", "jobs", "processing_events"):
        fk = next(
            fk
            for fk in Base.metadata.tables[table_name].foreign_keys
            if fk.column.table.name == "documents"
        )
        assert fk.ondelete == "CASCADE", table_name
