"""PostgreSQL adapter primitives for the initial snapshot vertical slice.

Requires psycopg 3. All identifiers are composed with psycopg.sql; values are
bound parameters. This module deliberately does not implement CDC yet.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Sequence

from snowbridge.contracts import Capability, CapabilityStatus, Column, Key, TableSchema

try:
    import psycopg
    from psycopg import sql
except ImportError:  # pragma: no cover
    psycopg = None
    sql = None


def _require_driver() -> None:
    if psycopg is None:
        raise RuntimeError("PostgreSQL adapter requires psycopg[binary]>=3.2")


@dataclass(frozen=True, slots=True)
class PostgresEndpoint:
    dsn: str
    connect_timeout: int = 10
    application_name: str = "snowbridge"


class PostgresAdapter:
    def __init__(self, endpoint: PostgresEndpoint):
        self.endpoint = endpoint

    def connect(self):
        _require_driver()
        return psycopg.connect(
            self.endpoint.dsn,
            connect_timeout=self.endpoint.connect_timeout,
            application_name=self.endpoint.application_name,
        )

    def inspect_capabilities(self) -> Sequence[Capability]:
        with self.connect() as conn:
            version_num = int(conn.execute("SHOW server_version_num").fetchone()[0])
            wal_level = conn.execute("SHOW wal_level").fetchone()[0]
            role = conn.execute(
                "SELECT rolsuper, rolreplication FROM pg_roles WHERE rolname = current_user"
            ).fetchone()
            can_replicate = bool(role and (role[0] or role[1]))
            logical_ready = version_num >= 90400 and wal_level == "logical" and can_replicate
            if version_num < 90400:
                logical_status = CapabilityStatus.UNAVAILABLE
                logical_reason = "Logical decoding requires PostgreSQL 9.4 or later."
            elif wal_level != "logical":
                logical_status = CapabilityStatus.REQUIRES_CONFIGURATION
                logical_reason = f"wal_level is {wal_level}; logical decoding requires wal_level=logical."
            elif not can_replicate:
                logical_status = CapabilityStatus.REQUIRES_PERMISSION
                logical_reason = "Current role needs REPLICATION or superuser privilege."
            else:
                logical_status = CapabilityStatus.AVAILABLE
                logical_reason = "Logical decoding configuration and current-role privilege checks passed."
            return (
                Capability("snapshot_repeatable_read", CapabilityStatus.AVAILABLE,
                           "PostgreSQL MVCC repeatable-read snapshots are available.",
                           min_version="9.2"),
                Capability("parallel_exported_snapshot",
                           CapabilityStatus.AVAILABLE if version_num >= 90200
                           else CapabilityStatus.UNAVAILABLE,
                           "pg_export_snapshot is available on supported PostgreSQL versions. "
                           "The exporting transaction must remain open until workers import it.",
                           min_version="9.2"),
                Capability("logical_decoding", logical_status, logical_reason,
                           requirements=("wal_level=logical", "replication slot privileges"),
                           permission_checks=("REPLICATION or superuser",)),
                Capability("copy_from_stdin", CapabilityStatus.AVAILABLE,
                           "COPY FROM STDIN is supported by PostgreSQL.", min_version="8.0"),
            )

    def discover_schema(self, include_schemas: Sequence[str] | None = None) -> list[TableSchema]:
        """Discover ordinary/partitioned tables and ordered columns/usable unique keys."""
        with self.connect() as conn:
            if include_schemas:
                rows = conn.execute(
                    """
                    SELECT n.nspname, c.relname, c.reltuples::bigint, c.relkind = 'p', pg_total_relation_size(c.oid)
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE c.relkind IN ('r','p') AND n.nspname = ANY(%s)
                    ORDER BY n.nspname, c.relname
                    """, (list(include_schemas),)
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT n.nspname, c.relname, c.reltuples::bigint, c.relkind = 'p'
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE c.relkind IN ('r','p')
                      AND n.nspname NOT IN ('pg_catalog','information_schema')
                      AND n.nspname NOT LIKE 'pg_toast%%'
                    ORDER BY n.nspname, c.relname
                    """
                ).fetchall()
            result: list[TableSchema] = []
            for schema_name, table_name, estimate, partitioned, estimated_bytes in rows:
                cols = conn.execute(
                    """
                    SELECT a.attname, a.attnum, format_type(a.atttypid,a.atttypmod),
                           NOT a.attnotnull,
                           CASE WHEN t.typname = 'timestamptz' THEN true
                                WHEN t.typname = 'timestamp' THEN false ELSE NULL END,
                           pg_get_expr(ad.adbin, ad.adrelid),
                           NULLIF(a.attgenerated, ''), NULLIF(a.attidentity, '')
                    FROM pg_attribute a
                    JOIN pg_class c ON c.oid=a.attrelid
                    JOIN pg_namespace n ON n.oid=c.relnamespace
                    JOIN pg_type t ON t.oid=a.atttypid
                    LEFT JOIN pg_attrdef ad ON ad.adrelid=a.attrelid AND ad.adnum=a.attnum
                    WHERE n.nspname=%s AND c.relname=%s
                      AND a.attnum > 0 AND NOT a.attisdropped
                    ORDER BY a.attnum
                    """, (schema_name, table_name)
                ).fetchall()
                key_rows = conn.execute(
                    """
                    SELECT i.relname, ix.indisprimary, ix.indisunique,
                           array_agg(a.attname ORDER BY k.ordinality)
                    FROM pg_index ix
                    JOIN pg_class t ON t.oid=ix.indrelid
                    JOIN pg_namespace n ON n.oid=t.relnamespace
                    JOIN pg_class i ON i.oid=ix.indexrelid
                    JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY k(attnum, ordinality) ON true
                    JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=k.attnum
                    WHERE n.nspname=%s AND t.relname=%s
                      AND (ix.indisprimary OR ix.indisunique)
                      AND ix.indpred IS NULL AND ix.indexprs IS NULL
                      AND k.ordinality <= ix.indnkeyatts
                      AND (
                        ix.indisprimary OR NOT EXISTS (
                          SELECT 1
                          FROM unnest(ix.indkey) WITH ORDINALITY nk(attnum, ordinality)
                          JOIN pg_attribute na ON na.attrelid=t.oid AND na.attnum=nk.attnum
                          WHERE nk.ordinality <= ix.indnkeyatts AND NOT na.attnotnull
                        )
                      )
                    GROUP BY i.relname, ix.indisprimary, ix.indisunique
                    ORDER BY ix.indisprimary DESC, i.relname
                    """, (schema_name, table_name)
                ).fetchall()
                columns = tuple(
                    Column(name=c[0], ordinal=int(c[1]), native_type=c[2],
                           nullable=bool(c[3]), timezone_aware=c[4],
                           default_expression=c[5], generated_kind=c[6] or None,
                           identity_kind=c[7] or None)
                    for c in cols
                )
                keys = tuple(Key(name=k[0], columns=tuple(k[3]),
                                 primary=bool(k[1]), unique=bool(k[2]))
                             for k in key_rows)
                result.append(TableSchema(schema_name, table_name, columns, keys,
                                          max(0, int(estimate)) if estimate is not None else None,
                                          bool(partitioned),
                                          estimated_bytes=max(0, int(estimated_bytes)) if estimated_bytes is not None else None,
                                          storage_engine="postgresql"))
            return result


def iter_keyset_rows(conn: Any, schema_name: str, table_name: str,
                     key_columns: Sequence[str], page_size: int,
                     start_after: Sequence[Any] | None = None) -> Iterator[tuple[Any, ...]]:
    """Yield bounded keyset pages for a stable, non-null unique key.

    The cursor description is used to find key positions; this does not assume
    primary-key columns are the first columns in physical table order.
    The caller must keep the connection in the imported snapshot transaction.
    Page limits bound row count, not serialized bytes; the byte-aware stream
    writer is still a required follow-up before production scale.
    """
    _require_driver()
    if not key_columns or page_size <= 0:
        raise ValueError("key_columns and positive page_size are required")
    table = sql.Identifier(schema_name, table_name)
    keys = sql.SQL(", ").join(map(sql.Identifier, key_columns))
    last = tuple(start_after) if start_after is not None else None
    while True:
        predicate = sql.SQL("TRUE") if last is None else sql.SQL("({}) > ({})").format(
            keys, sql.SQL(", ").join(sql.Placeholder() for _ in key_columns)
        )
        query = sql.SQL("SELECT * FROM {} WHERE {} ORDER BY {} LIMIT %s").format(
            table, predicate, keys
        )
        params = (page_size,) if last is None else (*last, page_size)
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            key_indexes = [next(i for i, d in enumerate(cur.description) if d.name == k)
                           for k in key_columns]
        if not rows:
            return
        for row in rows:
            yield row
        last = tuple(rows[-1][i] for i in key_indexes)


def copy_rows(conn: Any, schema_name: str, table_name: str,
              columns: Sequence[str], rows: Iterator[Sequence[Any]]) -> int:
    """Stream rows through COPY FROM STDIN within the caller-owned transaction."""
    _require_driver()
    if not columns:
        raise ValueError("COPY requires an explicit column list")
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(schema_name, table_name),
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
    )
    count = 0
    with conn.cursor() as cur:
        with cur.copy(statement) as copy:
            for row in rows:
                copy.write_row(row)
                count += 1
    return count



def integer_key_bounds(
    conn: Any, schema_name: str, table_name: str, key_column: str,
) -> tuple[int, int] | None:
    """Read indexed integer-key bounds inside the caller's snapshot transaction.

    This is a planning query, not a row-count estimate. Callers must first
    establish/import the run's exported MVCC snapshot so bounds and subsequent
    range reads observe the same source state.
    """
    _require_driver()
    if not schema_name or not table_name or not key_column:
        raise ValueError("schema, table and key column are required")
    query = sql.SQL("SELECT min({key}), max({key}) FROM {table}").format(
        key=sql.Identifier(key_column),
        table=sql.Identifier(schema_name, table_name),
    )
    minimum, maximum = conn.execute(query).fetchone()
    if minimum is None and maximum is None:
        return None
    if isinstance(minimum, bool) or isinstance(maximum, bool):
        raise TypeError("partition key must have an integral PostgreSQL type")
    if not isinstance(minimum, int) or not isinstance(maximum, int):
        raise TypeError(
            f"partition key {schema_name}.{table_name}.{key_column} is not an integral type"
        )
    return minimum, maximum



def iter_integer_key_chunk_rows(
    conn: Any,
    schema_name: str,
    table_name: str,
    key_column: str,
    lower_bound: int,
    upper_bound: int,
    *,
    upper_inclusive: bool = False,
    page_size: int = 10_000,
) -> Iterator[tuple[Any, ...]]:
    """Yield rows in one integer-key range using bounded keyset pages.

    The range predicate and continuation key are bound values; all identifiers
    are composed with psycopg.sql. The caller owns the connection transaction
    and must import the run's exported snapshot before invoking this reader.
    """
    _require_driver()
    if not schema_name or not table_name or not key_column:
        raise ValueError("schema, table and key column are required")
    if isinstance(lower_bound, bool) or isinstance(upper_bound, bool):
        raise TypeError("integer key bounds cannot be booleans")
    if not isinstance(lower_bound, int) or not isinstance(upper_bound, int):
        raise TypeError("integer key bounds must be integers")
    if upper_bound < lower_bound:
        raise ValueError("upper bound must be >= lower bound")
    if upper_bound == lower_bound and not upper_inclusive:
        raise ValueError("empty half-open range is not valid")
    if page_size <= 0:
        raise ValueError("page_size must be positive")

    key = sql.Identifier(key_column)
    table = sql.Identifier(schema_name, table_name)
    comparison = sql.SQL("<=") if upper_inclusive else sql.SQL("<")
    last_key: int | None = None
    while True:
        range_predicate = sql.SQL("{} >= %s AND {} {} %s").format(
            key, key, comparison
        )
        params: tuple[Any, ...] = (lower_bound, upper_bound)
        if last_key is not None:
            range_predicate = sql.SQL("({}) AND {} > %s").format(
                range_predicate, key
            )
            params = (*params, last_key)
        query = sql.SQL("SELECT * FROM {} WHERE {} ORDER BY {} LIMIT %s").format(
            table, range_predicate, key
        )
        with conn.cursor() as cur:
            cur.execute(query, (*params, page_size))
            rows = cur.fetchall()
            key_index = next(
                (i for i, description in enumerate(cur.description)
                 if description.name == key_column),
                None,
            )
        if key_index is None:
            raise RuntimeError(f"partition key {key_column!r} was not returned by SELECT")
        if not rows:
            return
        for row in rows:
            yield row
        last_key = rows[-1][key_index]
