"""Run durable migration jobs from metadata PostgreSQL.

Start one or more worker processes with: python -m app.worker
"""
import signal
import time

from app.services.migration_execution import claim_next_run, execute_run, recover_stale_runs

_shutdown = False


def _stop(*_args):
    global _shutdown
    _shutdown = True


def main():
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    last_recovery = 0.0
    while not _shutdown:
        now = time.monotonic()
        if now - last_recovery >= 30:
            recover_stale_runs()
            last_recovery = now
        run_id = claim_next_run()
        if run_id is None:
            time.sleep(2)
            continue
        execute_run(run_id)


if __name__ == "__main__":
    main()
