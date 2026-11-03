"""Guards for DECISIONS.md D17: no Supabase data clients anywhere.

The Supabase Data API is disabled. The backend reaches Postgres only through
SQLAlchemy, and files only through the Storage API. The frontend never talks
to Supabase at all.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BANNED_PYTHON = {"supabase", "postgrest", "supabase-py"}


def _python_packages(path: Path) -> set[str]:
    names = set()
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        names.add(re.split(r"[\[=<>!~ ]", line, maxsplit=1)[0].lower().replace("_", "-"))
    return names


def test_backend_has_no_supabase_table_client() -> None:
    for name in ("requirements.txt", "requirements-dev.txt"):
        packages = _python_packages(REPO / "backend" / name)
        assert packages, f"{name} parsed as empty"
        assert not (packages & BANNED_PYTHON), name


def test_frontend_has_no_supabase_packages() -> None:
    lock = json.loads((REPO / "frontend" / "package-lock.json").read_text())
    installed = {path.rsplit("node_modules/", 1)[-1] for path in lock["packages"] if path}
    assert installed, "package-lock.json parsed as empty"
    assert not any(name.startswith("@supabase/") for name in installed)
    assert "supabase" not in installed
