"""Resource-aware controls for production migration execution.

The scheduler is deliberately conservative: it budgets worker connections below
PostgreSQL's configured connection ceiling, accounts for local CPU capacity, and
uses bounded worker pools as the hard concurrency limit.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _positive_int(name: str, default: int, minimum: int = 1, maximum: int = 64) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class ConcurrencyPlan:
    workers: int
    connection_budget: int
    database_connections_in_use: int
    reason: str


class AdaptiveConcurrencyController:
    """Choose a safe writer count from DB headroom and local CPU capacity."""

    def __init__(self) -> None:
        self.minimum = _positive_int("CONDUIT_MIN_WRITERS", 1, 1, 16)
        self.maximum = _positive_int("CONDUIT_MAX_WRITERS", 4, 1, 32)
        self.reserve = _positive_int("CONDUIT_DB_CONNECTION_RESERVE", 5, 1, 100)
        self.cpu_factor = _positive_int("CONDUIT_CPU_WORKER_FACTOR", 2, 1, 8)

    def plan(self, destination_connection) -> ConcurrencyPlan:
        cpu_count = os.cpu_count() or 2
        cpu_limit = max(self.minimum, cpu_count * self.cpu_factor)
        max_connections = 0
        active_connections = 0
        try:
            with destination_connection.transaction():
                max_connections = int(
                    destination_connection.execute("SHOW max_connections").fetchone()[0]
                )
                active_connections = int(
                    destination_connection.execute(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database()"
                    ).fetchone()[0]
                )
        except Exception:
            # Lack of catalog visibility must not prevent a migration. Fall
            # back to a conservative fixed ceiling, never an unbounded pool.
            max_connections = 0
            active_connections = 0

        if max_connections > 0:
            headroom = max(1, max_connections - active_connections - self.reserve)
            connection_budget = min(self.maximum, headroom)
            reason = "database connection headroom and CPU budget"
        else:
            connection_budget = min(self.maximum, self.minimum)
            reason = "conservative fallback: database connection capacity unavailable"

        workers = max(self.minimum, min(self.maximum, cpu_limit, connection_budget))
        return ConcurrencyPlan(
            workers=workers,
            connection_budget=connection_budget,
            database_connections_in_use=active_connections,
            reason=reason,
        )


def resource_aware_table_order(tables, progress_by_plan_table):
    """Prioritize larger unfinished tables to reduce long-tail completion time."""
    def priority(table):
        progress = progress_by_plan_table.get(table.id)
        if progress and progress.status in {"completed", "partially_failed"}:
            return (1, 0, table.source_schema, table.source_table)
        estimate = int(getattr(progress, "total_rows", 0) or getattr(table, "estimated_rows", 0) or 0)
        return (0, -estimate, table.source_schema, table.source_table)

    return sorted(tables, key=priority)


def retry_delay(attempt: int) -> float:
    """Capped exponential backoff with deterministic jitter-free timing."""
    return min(0.5 * (2 ** max(0, attempt)), 8.0)
