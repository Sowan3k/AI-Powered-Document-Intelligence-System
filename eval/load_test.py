"""Throughput with 1, 2 and 4 workers on the real queue (D70).

Uploads the same batch of digital invoices for each worker count and lets
that many workers drain the Postgres queue at once. The model is the test
suite's perfect reader with a fixed delay per call, standing in for Gemini's
measured latency, so the numbers show how the queue scales, not Gemini's
speed. Workers run as threads: model calls wait on I/O, as real ones do.

    PYTHONPATH=.:../eval/generate python ../eval/load_test.py --docs 24
"""

import argparse
import json
import tempfile
import threading
import time
from pathlib import Path

from app.core.config import get_settings
from app.db.models import Document
from app.db.session import get_sessionmaker
from app.ingest.upload import register_upload
from app.storage.local import LocalStorage
from app.worker import queue
from app.worker.main import Worker
from sqlalchemy import func, select
from synth.dataset import build
from tests.conftest import FakeLlmClient
from tests.unit.extract.test_extract_fixtures import reader_for_truths

FILES = ["digital_classic_0.pdf", "digital_modern_0.pdf", "digital_european_0.pdf"]


def run(workers: int, docs: int, data: Path, latency_s: float, store: Path) -> float:
    settings = get_settings()
    truths = [json.loads((data / f"{f}.json").read_text()) for f in FILES]
    reader = reader_for_truths(truths)

    def slow(call):  # type: ignore[no-untyped-def]
        time.sleep(latency_s)  # stands in for one Gemini call
        return reader(call)

    llm = FakeLlmClient(slow)
    sessions = get_sessionmaker()
    storage = LocalStorage(store)
    with sessions() as session:
        for i in range(docs):
            name = FILES[i % len(FILES)]
            doc = register_upload(session, storage, name, data / name, settings)
            session.flush()
            queue.enqueue(session, doc.id, queue.JOB_PROCESS, settings)
            session.commit()

    def drain() -> None:
        worker = Worker(0.05, sessions=sessions, storage=storage, llm=llm, settings=settings,
                        heartbeats=False)  # fmt: skip
        while worker.run_once():
            pass

    started = time.monotonic()
    threads = [threading.Thread(target=drain) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.monotonic() - started
    with sessions() as session:
        done = session.scalar(select(func.count()).where(Document.status == "completed"))
        session.execute(Document.__table__.delete())  # next round starts empty
        session.commit()
    assert done == docs, f"only {done} of {docs} documents completed"
    return wall


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--docs", type=int, default=24)
    parser.add_argument("--latency", type=float, default=2.0, help="seconds per model call")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="docintel-load-") as tmp:
        data = Path(tmp) / "data"
        build(data, seed=7, scale=1)
        print(f"{args.docs} documents, {args.latency}s per model call")
        print("| Workers | Wall time | Documents a minute | Speed-up |")
        print("|---|---|---|---|")
        base = None
        for workers in (1, 2, 4):
            wall = run(workers, args.docs, data, args.latency, Path(tmp) / f"store{workers}")
            base = base or wall
            print(
                f"| {workers} | {wall:.1f} s | {args.docs / wall * 60:.0f} | {base / wall:.1f}x |"
            )


if __name__ == "__main__":
    main()
