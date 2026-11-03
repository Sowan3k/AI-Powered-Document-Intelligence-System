import signal
import threading

from app.worker.main import Worker


def test_stop_ends_the_loop_quickly() -> None:
    worker = Worker(poll_interval_s=30)
    thread = threading.Thread(target=worker.run)
    thread.start()
    worker.stop(signal.SIGTERM)
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_an_error_in_one_iteration_does_not_kill_the_loop() -> None:
    worker = Worker(poll_interval_s=0.01)
    calls = {"n": 0}

    def flaky_run_once() -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("bad job")
        if calls["n"] >= 3:
            worker.stop()
        return False

    worker.run_once = flaky_run_once  # type: ignore[method-assign]
    worker.run()
    assert calls["n"] >= 3


def test_runs_again_without_sleeping_when_work_was_done() -> None:
    worker = Worker(poll_interval_s=60)
    calls = {"n": 0}

    def busy_run_once() -> bool:
        calls["n"] += 1
        if calls["n"] == 5:
            worker.stop()
        return True

    worker.run_once = busy_run_once  # type: ignore[method-assign]
    worker.run()  # would take minutes if it slept between jobs
    assert calls["n"] == 5


def test_worker_id_names_host_and_process() -> None:
    assert ":" in Worker(poll_interval_s=1).worker_id
