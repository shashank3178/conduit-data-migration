"""Compare Psycopg row-wise COPY in text and binary formats.

Run with CONDUIT_BENCHMARK_DSN set to a disposable PostgreSQL database:
    python scripts/benchmark_copy_formats.py --rows 100000 --repeats 3

This measures client adaptation + COPY transport + server ingest on the same
connection. It does not benchmark the production staging merge.
"""
from __future__ import annotations

import argparse
import os
import statistics
import time

import psycopg


def benchmark(connection, row_count: int, repeats: int, copy_format: str) -> list[float]:
    timings = []
    suffix = " (FORMAT BINARY)" if copy_format == "binary" else ""
    query = f"COPY conduit_copy_benchmark (id, payload) FROM STDIN{suffix}"

    for _ in range(repeats):
        connection.execute("TRUNCATE conduit_copy_benchmark")
        started = time.perf_counter()
        with connection.cursor().copy(query) as copy:
            if copy_format == "binary":
                copy.set_types(["int8", "text"])
            for row_id in range(row_count):
                copy.write_row((row_id, f"payload-{row_id:012d}-" + ("x" * 96)))
        elapsed = time.perf_counter() - started
        actual = connection.execute("SELECT count(*) FROM conduit_copy_benchmark").fetchone()[0]
        if actual != row_count:
            raise RuntimeError(f"{copy_format} COPY inserted {actual:,} rows; expected {row_count:,}")
        timings.append(elapsed)
    return timings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    dsn = os.getenv("CONDUIT_BENCHMARK_DSN")
    if not dsn:
        raise SystemExit("Set CONDUIT_BENCHMARK_DSN to a disposable PostgreSQL DSN.")
    if args.rows < 1 or args.repeats < 1:
        raise SystemExit("--rows and --repeats must be positive.")

    with psycopg.connect(dsn) as connection:
        connection.execute(
            "CREATE TEMP TABLE conduit_copy_benchmark "
            "(id BIGINT PRIMARY KEY, payload TEXT) ON COMMIT PRESERVE ROWS"
        )
        results = {}
        for copy_format in ("text", "binary"):
            timings = benchmark(connection, args.rows, args.repeats, copy_format)
            median = statistics.median(timings)
            results[copy_format] = median
            print(
                f"{copy_format:>6} COPY: median={median:.3f}s, "
                f"rows/s={args.rows / median:,.0f}, "
                f"MB/s={(args.rows * 120) / median / 1_000_000:.2f}"
            )

    if results["binary"] > 0:
        print(f"Binary speedup: {results['text'] / results['binary']:.2f}x")


if __name__ == "__main__":
    main()
