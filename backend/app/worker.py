"""Run durable migration jobs from metadata PostgreSQL."""
import os
import signal
import socket
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import UTC, datetime

from app.db.session import SessionLocal
from app.models.migration_run import MigrationRun
from app.services.migration_execution import claim_next_run, execute_run, recover_stale_runs

_shutdown = False


def _stop(*_args):
    global _shutdown
    _shutdown = True


def _heartbeat(run_id, worker_id, stop_event):
    interval = max(5, int(os.getenv("CONDUIT_WORKER_HEARTBEAT_SECONDS", "20")))
    while not stop_event.wait(interval):
        with SessionLocal() as db:
            run = db.get(MigrationRun, run_id)
            if run is None or run.status != "running" or run.worker_id != worker_id:
                return
            run.heartbeat_at = datetime.now(UTC)
            db.commit()


def _execute_claimed(run_id, worker_id):
    stop_event = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat, args=(run_id, worker_id, stop_event),
        name=f"conduit-heartbeat-{worker_id}", daemon=True,
    )
    heartbeat.start()
    try:
        execute_run(run_id, worker_id=worker_id)
    finally:
        stop_event.set()
        heartbeat.join(timeout=2)


def main():
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    worker_id = os.getenv("CONDUIT_WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    poll_seconds = max(0.25, float(os.getenv("CONDUIT_WORKER_POLL_SECONDS", "2")))
    stale_seconds = max(60, int(os.getenv("CONDUIT_WORKER_STALE_SECONDS", "1800")))
    concurrency = max(1, min(32, int(os.getenv("CONDUIT_WORKER_CONCURRENCY", "1"))))
    last_recovery = 0.0

    # Every run owns independent source/destination connections and a metadata
    # Session. PostgreSQL SKIP LOCKED coordinates this pool with other workers.
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="conduit-run") as pool:
        active = set()
        while not _shutdown:
            completed = {future for future in active if future.done()}
            for future in completed:
                try:
                    future.result()
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception("Unexpected migration worker task failure")
            active.difference_update(completed)

            now = time.monotonic()
            if now - last_recovery >= 30:
                recover_stale_runs(stale_after_seconds=stale_seconds)
                last_recovery = now

            while len(active) < concurrency and not _shutdown:
                run_id = claim_next_run(worker_id=worker_id)
                if run_id is None:
                    break
                active.add(pool.submit(_execute_claimed, run_id, worker_id))

            if active:
                wait(active, timeout=poll_seconds, return_when=FIRST_COMPLETED)
            else:
                time.sleep(poll_seconds)

        # Let in-flight batches finish their current destination transaction
        # and persist the next checkpoint before process shutdown completes.
        for future in active:
            future.result()


if __name__ == "__main__":
    main()
