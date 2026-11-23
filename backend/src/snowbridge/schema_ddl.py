"""Conservative PostgreSQL-to-PostgreSQL target DDL generation.

Only built-in PostgreSQL types and structurally representable constraints are
accepted. Arbitrary source SQL expressions, domains, enums, arrays, generated
columns and partitioning are rejected rather than copied into target SQL.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from snowbridge.contracts import Column, TableSchema

try:
    from psycopg import sql
except ImportError:  # pragma: no cover
    sql = None


_TYPE_PATTERNS = (
    (re.compile(r"^(smallint|integer|bigint|real|double precision|boolean|"
                r"text|bytea|date|uuid|json|jsonb|xml|inet|cidr|macaddr|"
                r"money)$", re.I), None),
    (re.compile(r"^(character varying|varchar|character|char)\((\d+)\)$", re.I), None),
    (re.compile(r"^(numeric|decimal)\((\d+),\s*(\d+)\)$", re.I), None),
    (re.compile(r"^(numeric|decimal)\((\d+)\)$", re.I), None),
    (re.compile(r"^(timestamp|time) with time zone$", re.I), None),
    (re.compile(r"^(timestamp|time) without time zone$", re.I), None),
    (re.compile(r"^(timestamp|time)$", re.I), None),
    (re.compile(r"^bit varying\((\d+)\)$", re.I), None),
    (re.compile(r"^bit\((\d+)\)$", re.I), None),
)


class UnsupportedSchemaError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DDLPlan:
    statements: tuple[Any, ...]
    load_columns: tuple[tuple[str, str, tuple[str, ...]], ...]
    diagnostics: tuple[str, ...]


def _type_sql(native_type: str):
    value = " ".join(native_type.strip().split())
    for pattern, _ in _TYPE_PATTERNS:
        match = pattern.fullmatch(value)
        if match:
            # Type text is reconstructed from an allowlisted grammar; no
            # arbitrary catalog-provided type fragment reaches SQL execution.
            groups = match.groups()
            if len(groups) == 1 and groups[0] and groups[0].isdigit():
                return sql.SQL("{}({})").format(sql.SQL(pattern.pattern.split("^")[1].split("|")[0]),
                                                 sql.Literal(int(groups[0])))
            if len(groups) == 2 and all(g and g.isdigit() for g in groups):
                base = "numeric" if value.lower().startswith(("numeric", "decimal")) else "varchar"
                if value.lower().startswith(("character varying", "varchar")):
                    base = "varchar"
                elif value.lower().startswith(("character(", "char(")):
                    base = "char"
                return sql.SQL("{}({},{})").format(
                    sql.SQL(base), sql.Literal(int(groups[0])), sql.Literal(int(groups[1]))
                )
            # Exact simple type names are safe only after a full regex match.
            if not groups:
                return sql.SQL(value)
            if value.lower().startswith(("timestamp", "time")):
                return sql.SQL(value)
            if value.lower().startswith("bit"):
                base = "varbit" if value.lower().startswith("bit varying") else "bit"
                return sql.SQL("{}({})").format(sql.SQL(base), sql.Literal(int(groups[0])))
    raise UnsupportedSchemaError(
        f"unsupported PostgreSQL type {native_type!r}; custom types, arrays and "
        "unrecognized type modifiers require an explicit mapping"
    )


def _safe_default(expression: str) -> bool:
    value = expression.strip()
    return bool(
        re.fullmatch(r"-?\d+(?:\.\d+)?", value)
        or re.fullmatch(r"'(?:[^']|'')*'(?:::[\w ]+)?", value)
        or value.upper() in {"TRUE", "FALSE", "NULL", "CURRENT_TIMESTAMP",
                             "CURRENT_DATE", "CURRENT_TIME"}
        or value.lower() in {"now()", "localtimestamp", "localtime"}
    )


def plan_postgresql_ddl(tables: Sequence[TableSchema]) -> DDLPlan:
    if sql is None:
        raise RuntimeError("PostgreSQL DDL generation requires psycopg")
    statements: list[Any] = []
    diagnostics: list[str] = []
    load_columns: list[tuple[str, str, tuple[str, ...]]] = []
    schemas = sorted({table.schema_name for table in tables})
    for schema_name in schemas:
        statements.append(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
            sql.Identifier(schema_name)
        ))

    for table in tables:
        qualified = f"{table.schema_name}.{table.table_name}"
        if table.partitioned:
            raise UnsupportedSchemaError(
                f"{qualified}: partitioned tables require an explicit partition strategy"
            )
        if not table.columns:
            raise UnsupportedSchemaError(f"{qualified}: table has no discoverable columns")
        definitions = []
        writable = []
        for column in sorted(table.columns, key=lambda c: c.ordinal):
            if column.generated_kind:
                raise UnsupportedSchemaError(
                    f"{qualified}.{column.name}: generated columns are not yet translated"
                )
            definition = sql.SQL("{} {}").format(
                sql.Identifier(column.name), _type_sql(column.native_type)
            )
            if column.identity_kind:
                mode = "ALWAYS" if column.identity_kind == "a" else "BY DEFAULT"
                definition += sql.SQL(" GENERATED {} AS IDENTITY").format(sql.SQL(mode))
            elif column.default_expression:
                if _safe_default(column.default_expression):
                    definition += sql.SQL(" DEFAULT {}").format(
                        sql.SQL(column.default_expression.strip())
                    )
                else:
                    diagnostics.append(
                        f"{qualified}.{column.name}: source default "
                        f"{column.default_expression!r} was not copied; requires review"
                    )
            if not column.nullable:
                definition += sql.SQL(" NOT NULL")
            definitions.append(definition)
            if not column.generated_kind:
                writable.append(column.name)

        for key in table.keys:
            if not key.columns:
                continue
            key_columns = sql.SQL(", ").join(sql.Identifier(c) for c in key.columns)
            if key.primary:
                definitions.append(sql.SQL("CONSTRAINT {} PRIMARY KEY ({})").format(
                    sql.Identifier(key.name), key_columns
                ))
            elif key.unique:
                definitions.append(sql.SQL("CONSTRAINT {} UNIQUE ({})").format(
                    sql.Identifier(key.name), key_columns
                ))
        statements.append(sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
            sql.Identifier(table.schema_name, table.table_name),
            sql.SQL(", ").join(definitions),
        ))
        load_columns.append((table.schema_name, table.table_name, tuple(writable)))

    return DDLPlan(tuple(statements), tuple(load_columns), tuple(diagnostics))


def apply_postgresql_ddl(conn: Any, tables: Sequence[TableSchema]) -> DDLPlan:
    """Apply a generated DDL plan in the caller-owned target transaction."""
    plan = plan_postgresql_ddl(tables)
    for statement in plan.statements:
        conn.execute(statement)
    return plan
