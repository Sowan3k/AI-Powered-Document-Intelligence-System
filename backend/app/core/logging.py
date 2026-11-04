"""Logging setup shared by the API and the worker.

Logs carry IDs, statuses and timings. They never carry raw document text or
extracted personal data (CLAUDE.md, security rule 8).
"""

import logging
import sys

_FORMAT = "%(asctime)s %(levelname)s %(process)d %(name)s: %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Send all logs to stdout in one plain format. Safe to call twice."""
    root = logging.getLogger()
    root.setLevel(level)
    if not any(getattr(h, "_docintel", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_FORMAT))
        handler._docintel = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    # SQL echo would print query parameters, which can hold extracted data.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    # One line per HTTP request is noise; DocIntel logs its own calls with timings.
    for name in ("httpx", "httpx2", "google_genai"):
        logging.getLogger(name).setLevel(logging.WARNING)
