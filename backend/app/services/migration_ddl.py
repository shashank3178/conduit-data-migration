import re

from fastapi import HTTPException

_IDENTIFIER_MAX = 63
_TYPE_PATTERN = re.compile(
    r"^(SMALLINT|INT2|INTEGER|INT|INT4|BIGINT|INT8|BOOLEAN|BOOL|TEXT|"
    r"VARCHAR(?:\s*\(\s*\d+\s*\))?|CHARACTER VARYING(?:\s*\(\s*\d+\s*\))?|"
    r"CHAR(?:ACTER)?(?:\s*\(\s*\d+\s*\))?|"
    r"NUMERIC(?:\s*\(\s*\d+\s*(?:,\s*\d+\s*)?\))?|DECIMAL(?:\s*\(\s*\d+\s*(?:,\s*\d+\s*)?\))?|"
    r"REAL|FLOAT4|DOUBLE PRECISION|FLOAT8|DATE|"
    r"TIME(?:\s*\(\s*\d+\s*\))?(?: WITH(?:OUT)? TIME ZONE)?|"
    r"TIMESTAMP(?:\s*\(\s*\d+\s*\))?(?: WITH(?:OUT)? TIME ZONE)?|"
    r"UUID|JSONB?|BYTEA|INET|CIDR|MACADDR|XML)(\[\])?$",
    re.IGNORECASE,
)


def quote_identifier(value: str) -> str:
    if not value or len(value) > _IDENTIFIER_MAX or "\x00" in value:
        raise HTTPException(status_code=422, detail="Invalid PostgreSQL identifier in migration plan.")
    return '"' + value.replace('"', '""') + '"'


def normalize_pg_type(value: str | None) -> str | None:
    if not value:
        return None
    candidate = " ".join(value.strip().upper().split())
    if not _TYPE_PATTERN.fullmatch(candidate):
        return None
    aliases = {
        "INT2": "SMALLINT",
        "INT": "INTEGER",
        "INT4": "INTEGER",
        "INT8": "BIGINT",
        "BOOL": "BOOLEAN",
        "FLOAT4": "REAL",
        "FLOAT8": "DOUBLE PRECISION",
    }
    array_suffix = "[]" if candidate.endswith("[]") else ""
    base = candidate[:-2] if array_suffix else candidate
    base = aliases.get(base, base)
    if base.startswith("CHARACTER VARYING"):
        base = base.replace("CHARACTER VARYING", "VARCHAR", 1)
    return base + array_suffix


def types_compatible(source: str | None, destination: str | None) -> bool:
    src = normalize_pg_type(source)
    dst = normalize_pg_type(destination)
    if not src or not dst:
        return False
    if src == dst:
        return True
    integer_rank = {"SMALLINT": 1, "INTEGER": 2, "BIGINT": 3}
    if src in integer_rank and dst in integer_rank:
        return integer_rank[dst] >= integer_rank[src]
    numeric = {"REAL": 1, "DOUBLE PRECISION": 2}
    if src in numeric and dst in numeric:
        return numeric[dst] >= numeric[src]
    if src.startswith("VARCHAR") and dst.startswith("VARCHAR"):
        def length(value: str) -> int | None:
            match = re.search(r"\((\d+)\)", value)
            return int(match.group(1)) if match else None
        source_length, destination_length = length(src), length(dst)
        return destination_length is None or (
            source_length is not None and destination_length >= source_length
        )
    return False


def build_ddl(plan_tables, mappings_by_table, create_schemas: bool):
    statements: list[str] = []
    warnings: list[str] = []
    schemas: set[str] = set()
    tables_to_create = 0

    for table in plan_tables:
        if not table.selected or table.destination_exists:
            continue
        if table.source_table_type != "table":
            warnings.append(
                f"{table.source_schema}.{table.source_table} is a {table.source_table_type}; only regular tables can be created."
            )
            continue

        schema = table.destination_schema
        target = f"{quote_identifier(schema)}.{quote_identifier(table.destination_table)}"
        if create_schemas:
            schemas.add(schema)

        mappings = {
            item.source_column: item
            for item in mappings_by_table.get(table.id, [])
            if item.included and item.destination_column
        }
        definitions: list[str] = []
        source_to_target: dict[str, str] = {}
        for column in table.source_columns:
            source_name = column.get("name")
            mapping = mappings.get(source_name)
            if not mapping:
                continue
            pg_type = normalize_pg_type(mapping.destination_type or mapping.source_type)
            if not pg_type:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unsupported PostgreSQL type for {table.source_schema}.{table.source_table}.{source_name}. Set a supported destination type or exclude the column.",
                )
            definition = f"{quote_identifier(mapping.destination_column)} {pg_type}"
            if not column.get("nullable", True):
                definition += " NOT NULL"
            definitions.append(definition)
            source_to_target[source_name] = mapping.destination_column
            if column.get("default") is not None:
                warnings.append(
                    f"Default expression for {table.source_schema}.{table.source_table}.{source_name} was omitted for safety."
                )

        if not definitions:
            warnings.append(f"No included columns are mapped for {table.source_schema}.{table.source_table}.")
            continue

        pk_columns = (table.source_primary_key or {}).get("constrained_columns") or []
        mapped_pk = [source_to_target[name] for name in pk_columns if name in source_to_target]
        if pk_columns and len(mapped_pk) == len(pk_columns):
            definitions.append(
                "PRIMARY KEY (" + ", ".join(quote_identifier(name) for name in mapped_pk) + ")"
            )
        elif pk_columns:
            warnings.append(
                f"Primary key for {table.source_schema}.{table.source_table} was omitted because not all key columns are mapped."
            )

        statements.append(f"CREATE TABLE IF NOT EXISTS {target} (\n  " + ",\n  ".join(definitions) + "\n);")
        tables_to_create += 1

        if table.source_primary_key and table.source_primary_key.get("name"):
            pass
        if table.destination_schema != table.source_schema:
            warnings.append(
                f"Table {table.source_schema}.{table.source_table} is being mapped to {table.destination_schema}.{table.destination_table}."
            )
        if table.source_table_type == "table":
            warnings.append(
                f"Foreign keys, check constraints, indexes, identity properties, and generated/default expressions are not included for {table.source_schema}.{table.source_table}; review them before a production migration."
            )

    schema_statements = [
        f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(schema)};"
        for schema in sorted(schemas)
    ]
    return schema_statements + statements, warnings, tables_to_create, sorted(schemas)
