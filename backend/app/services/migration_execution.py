"""Batch migration runner. In-process background execution is for local/demo use."""
import uuid
from datetime import datetime, timezone

import psycopg
from psycopg import sql
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.connection import DatabaseConnection
from app.models.migration_plan import MigrationColumnMapping, MigrationPlan, MigrationPlanTable
from app.models.migration_run import MigrationRun, MigrationRunTable
from app.services.connection_service import decrypt_password


def _connect(record: DatabaseConnection):
    return psycopg.connect(
        host=record.host, port=record.port, dbname=record.database, user=record.username,
        password=decrypt_password(record.password_encrypted), sslmode=record.sslmode,
        connect_timeout=10, application_name="Conduit migration",
    )


def _cancel_requested(run_id: uuid.UUID) -> bool:
    with SessionLocal() as db:
        run = db.get(MigrationRun, run_id)
        return run is None or run.status == "cancel_requested"


def execute_run(run_id: uuid.UUID) -> None:
    """Fetch source rows in bounded batches and commit each destination batch."""
    db = SessionLocal()
    source = destination = None
    try:
        run = db.get(MigrationRun, run_id)
        if not run or run.status != "queued":
            return
        plan = db.get(MigrationPlan, run.plan_id)
        run.status, run.started_at = "running", datetime.now(timezone.utc)
        db.commit()
        source = _connect(db.get(DatabaseConnection, plan.source_connection_id))
        destination = _connect(db.get(DatabaseConnection, plan.destination_connection_id))
        tables = db.query(MigrationPlanTable).filter_by(plan_id=plan.id, selected=True).order_by(
            MigrationPlanTable.source_schema, MigrationPlanTable.source_table
        ).all()

        for table in tables:
            if _cancel_requested(run_id):
                break
            progress = db.query(MigrationRunTable).filter_by(run_id=run_id, plan_table_id=table.id).one()
            progress.status = "running"
            exact_count = source.execute(
                sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                    sql.Identifier(table.source_schema), sql.Identifier(table.source_table)
                )
            ).fetchone()[0]
            progress.total_rows = exact_count
            run.total_rows += exact_count
            db.commit()
            mappings = db.query(MigrationColumnMapping).filter_by(
                plan_table_id=table.id, included=True
            ).order_by(MigrationColumnMapping.source_column).all()
            pairs = [(m.source_column, m.destination_column) for m in mappings if m.destination_column]
            if not pairs:
                progress.status, progress.error_message = "failed", "No included column mappings."
                run.failed_rows += 1
                db.commit()
                continue

            source_cols, destination_cols = [s for s, _ in pairs], [d for _, d in pairs]
            select_query = sql.SQL("SELECT {} FROM {}.{}").format(
                sql.SQL(", ").join(map(sql.Identifier, source_cols)),
                sql.Identifier(table.source_schema), sql.Identifier(table.source_table),
            )
            insert_query = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
                sql.Identifier(table.destination_schema), sql.Identifier(table.destination_table),
                sql.SQL(", ").join(map(sql.Identifier, destination_cols)),
                sql.SQL(", ").join(sql.Placeholder() for _ in destination_cols),
            )
            with source.cursor(name=f"conduit_{str(table.id).replace('-', '')[:20]}") as reader:
                reader.itersize = run.batch_size
                reader.execute(select_query)
                while True:
                    if _cancel_requested(run_id):
                        break
                    batch = reader.fetchmany(run.batch_size)
                    if not batch:
                        break
                    with destination.cursor() as writer:
                        writer.executemany(insert_query, batch)
                    destination.commit()
                    progress.migrated_rows += len(batch)
                    run.migrated_rows += len(batch)
                    db.commit()

            if progress.status == "running":
                progress.status = "completed"
                run.completed_tables += 1
                db.commit()

        run.status = "cancelled" if _cancel_requested(run_id) else (
            "partially_failed" if run.failed_rows else "completed"
        )
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        failed = db.get(MigrationRun, run_id)
        if failed:
            failed.status = "failed"
            failed.error_message = str(exc).splitlines()[0][:500]
            failed.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        if source:
            source.close()
        if destination:
            destination.close()
        db.close()
