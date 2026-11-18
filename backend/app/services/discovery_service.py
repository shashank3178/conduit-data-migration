import uuid
from datetime import UTC, datetime

import psycopg
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from app.models.connection import DatabaseConnection
from app.models.discovery import DiscoveredSchema, DiscoveredTable, DiscoverySnapshot
from app.models.user import User
from app.services.connection_service import decrypt_password, get_connection

SYSTEM_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast"}


def _engine_for(connection: DatabaseConnection):
    return create_engine(
        URL.create(
            "postgresql+psycopg",
            username=connection.username,
            password=decrypt_password(connection.password_encrypted),
            host=connection.host,
            port=connection.port,
            database=connection.database,
            query={"sslmode": connection.sslmode, "connect_timeout": "8"},
        ),
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
    )


def _safe_error(exc: Exception) -> str:
    # Avoid returning DSNs, usernames, or credentials in exception text.
    if isinstance(exc, psycopg.OperationalError):
        return "Could not connect to PostgreSQL. Verify host, port, database, credentials, network access, and SSL settings."
    return f"Database discovery failed ({type(exc).__name__}). Check database permissions and retry."


def _plain(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    # SQLAlchemy TypeEngine and SQL expression defaults are not JSON-native.
    if value.__class__.__module__.startswith("sqlalchemy"):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def discover(db: Session, user: User, project_id: uuid.UUID, connection_id: uuid.UUID) -> DiscoverySnapshot:
    connection = get_connection(db, user, project_id, connection_id)
    engine = _engine_for(connection)
    try:
        with engine.connect() as conn:
            inspector = inspect(conn)
            database_name = conn.execute(text("SELECT current_database()")).scalar_one()
            server_version = conn.execute(text("SELECT version()")).scalar_one().splitlines()[0][:255]
            database_size_bytes = int(conn.execute(text("SELECT pg_database_size(current_database())")).scalar_one())
            schemas = sorted(inspector.get_schema_names())
            snapshot = db.query(DiscoverySnapshot).filter_by(connection_id=connection.id).first()
            if snapshot is None:
                snapshot = DiscoverySnapshot(
                    project_id=project_id,
                    connection_id=connection.id,
                    database_name=database_name,
                    status="running",
                )
                db.add(snapshot)
                db.flush()
            else:
                snapshot.status = "running"
                snapshot.database_name = database_name
                snapshot.server_version = server_version
                snapshot.error_message = None
                db.query(DiscoveredSchema).filter_by(snapshot_id=snapshot.id).delete(
                    synchronize_session=False
                )
                db.flush()

            snapshot.server_version = server_version
            snapshot.database_size_bytes = database_size_bytes
            schema_count = 0
            table_count = 0
            for schema_name in schemas:
                is_system = schema_name in SYSTEM_SCHEMAS or schema_name.startswith("pg_toast")
                schema_record = DiscoveredSchema(
                    snapshot_id=snapshot.id,
                    name=schema_name,
                    is_system=is_system,
                )
                db.add(schema_record)
                db.flush()
                schema_count += 1
                if is_system:
                    continue

                table_names = inspector.get_table_names(schema=schema_name)
                view_names = inspector.get_view_names(schema=schema_name)
                materialized_views = conn.execute(
                    text(
                        """
                        SELECT c.relname
                        FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = :schema AND c.relkind = 'm'
                        """
                    ),
                    {"schema": schema_name},
                ).scalars().all()

                for table_name in sorted(set(table_names) | set(view_names) | set(materialized_views)):
                    if table_name in materialized_views:
                        kind = "materialized_view"
                    elif table_name in view_names:
                        kind = "view"
                    else:
                        kind = "table"

                    columns = [_plain(column) for column in inspector.get_columns(table_name, schema=schema_name)]
                    primary_key = _plain(inspector.get_pk_constraint(table_name, schema=schema_name) or {})
                    foreign_keys = [_plain(item) for item in inspector.get_foreign_keys(table_name, schema=schema_name)]
                    unique_constraints = [_plain(item) for item in inspector.get_unique_constraints(table_name, schema=schema_name)]
                    check_constraints = [_plain(item) for item in inspector.get_check_constraints(table_name, schema=schema_name)]
                    indexes = [_plain(item) for item in inspector.get_indexes(table_name, schema=schema_name)]
                    comment = inspector.get_table_comment(table_name, schema=schema_name).get("text")
                    size_stats = conn.execute(
                        text("""
                            SELECT pg_total_relation_size(format('%I.%I', :schema, :table))::bigint AS total_bytes,
                                   pg_table_size(format('%I.%I', :schema, :table))::bigint AS table_bytes,
                                   pg_indexes_size(format('%I.%I', :schema, :table))::bigint AS index_bytes
                        """),
                        {"schema": schema_name, "table": table_name},
                    ).mappings().one() if kind != "view" else {"total_bytes": 0, "table_bytes": 0, "index_bytes": 0}
                    estimate = conn.execute(
                        text(
                            """
                            SELECT COALESCE(s.n_live_tup, 0)::bigint
                            FROM pg_stat_user_tables s
                            JOIN pg_class c ON c.relname = s.relname
                            JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = s.schemaname
                            WHERE s.schemaname = :schema AND s.relname = :table
                            """
                        ),
                        {"schema": schema_name, "table": table_name},
                    ).scalar_one_or_none()

                    db.add(
                        DiscoveredTable(
                            schema_id=schema_record.id,
                            name=table_name,
                            table_type=kind,
                            estimated_rows=int(estimate) if estimate is not None else None,
                            total_size_bytes=int(size_stats["total_bytes"]),
                            table_size_bytes=int(size_stats["table_bytes"]),
                            index_size_bytes=int(size_stats["index_bytes"]),
                            columns=columns,
                            primary_key=primary_key,
                            foreign_keys=foreign_keys,
                            unique_constraints=unique_constraints,
                            check_constraints=check_constraints,
                            indexes=indexes,
                            comment=comment,
                        )
                    )
                    table_count += 1

            snapshot.status = "completed"
            snapshot.schema_count = schema_count
            snapshot.table_count = table_count
            snapshot.discovered_at = datetime.now(UTC)
            snapshot.error_message = None
            db.commit()
            db.refresh(snapshot)
            return snapshot
    except Exception as exc:
        db.rollback()
        existing = db.query(DiscoverySnapshot).filter_by(connection_id=connection.id).first()
        if existing:
            existing.status = "failed"
            existing.error_message = _safe_error(exc)
            db.commit()
        raise HTTPException(status_code=502, detail=_safe_error(exc)) from exc
    finally:
        engine.dispose()


def get_snapshot(db: Session, user: User, project_id: uuid.UUID, connection_id: uuid.UUID) -> DiscoverySnapshot:
    get_connection(db, user, project_id, connection_id)
    snapshot = db.query(DiscoverySnapshot).filter_by(
        project_id=project_id, connection_id=connection_id
    ).first()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No discovery has been run for this connection.")
    return snapshot


def list_schemas(db: Session, user: User, project_id: uuid.UUID, connection_id: uuid.UUID):
    snapshot = get_snapshot(db, user, project_id, connection_id)
    rows = db.query(DiscoveredSchema).filter_by(snapshot_id=snapshot.id).order_by(
        DiscoveredSchema.name
    ).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "is_system": row.is_system,
            "table_count": db.query(DiscoveredTable).filter_by(schema_id=row.id).count(),
        }
        for row in rows
    ]


def list_tables(
    db: Session,
    user: User,
    project_id: uuid.UUID,
    connection_id: uuid.UUID,
    schema_name: str | None = None,
):
    snapshot = get_snapshot(db, user, project_id, connection_id)
    query = (
        db.query(DiscoveredTable, DiscoveredSchema.name)
        .join(DiscoveredSchema)
        .filter(DiscoveredSchema.snapshot_id == snapshot.id)
    )
    if schema_name:
        query = query.filter(DiscoveredSchema.name == schema_name)
    return [
        {
            "id": table.id,
            "schema_name": schema,
            "name": table.name,
            "table_type": table.table_type,
            "estimated_rows": table.estimated_rows,
            "total_size_bytes": table.total_size_bytes,
            "table_size_bytes": table.table_size_bytes,
            "index_size_bytes": table.index_size_bytes,
        }
        for table, schema in query.order_by(DiscoveredSchema.name, DiscoveredTable.name).all()
    ]


def get_table(
    db: Session,
    user: User,
    project_id: uuid.UUID,
    connection_id: uuid.UUID,
    table_id: uuid.UUID,
):
    get_snapshot(db, user, project_id, connection_id)
    result = (
        db.query(DiscoveredTable, DiscoveredSchema.name)
        .join(DiscoveredSchema)
        .join(DiscoverySnapshot)
        .filter(
            DiscoverySnapshot.project_id == project_id,
            DiscoverySnapshot.connection_id == connection_id,
            DiscoveredTable.id == table_id,
        )
        .first()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Discovered table not found.")
    table, schema_name = result
    return {
        "id": table.id,
        "schema_name": schema_name,
        "name": table.name,
        "table_type": table.table_type,
        "estimated_rows": table.estimated_rows,
        "total_size_bytes": table.total_size_bytes,
        "table_size_bytes": table.table_size_bytes,
        "index_size_bytes": table.index_size_bytes,
        "columns": table.columns,
        "primary_key": table.primary_key,
        "foreign_keys": table.foreign_keys,
        "unique_constraints": table.unique_constraints,
        "check_constraints": table.check_constraints,
        "indexes": table.indexes,
        "comment": table.comment,
    }
