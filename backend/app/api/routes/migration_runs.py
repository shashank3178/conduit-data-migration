import csv
import io
import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models.migration_metrics import (
    MigrationBatchMetric,
    MigrationRunMetric,
    MigrationTableMetric,
)
from app.models.migration_plan import MigrationColumnMapping, MigrationPlanTable
from app.models.migration_run import (
    MigrationRowError,
    MigrationRun,
    MigrationRunEvent,
    MigrationRunTable,
)
from app.models.user import User
from app.schemas.migration_run import (
    MigrationRowErrorResponse,
    MigrationRunCreate,
    MigrationRunEventResponse,
    MigrationRunResponse,
    MigrationRunTableResponse,
)
from app.services.migration_plan_service import get_plan

router = APIRouter(prefix="/projects/{project_id}/migration-plans/{plan_id}/runs", tags=["Migration execution"])


def _owned_run(db: Session, user: User, project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID):
    run = db.query(MigrationRun).filter_by(
        id=run_id, project_id=project_id, owner_id=user.id, plan_id=plan_id
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Migration run not found.")
    return run


@router.post("", response_model=MigrationRunResponse, status_code=status.HTTP_202_ACCEPTED)
def start_run(
    project_id: uuid.UUID, plan_id: uuid.UUID, payload: MigrationRunCreate,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    plan = get_plan(db, user, project_id, plan_id)
    if plan.status not in {"ready", "schema_prepared"}:
        raise HTTPException(status_code=409, detail="Validate the plan and prepare destination tables before starting execution.")
    selected = db.query(MigrationPlanTable).filter_by(plan_id=plan.id, selected=True).all()
    if not selected:
        raise HTTPException(status_code=422, detail="Select at least one source table.")
    if any(not table.destination_exists for table in selected):
        raise HTTPException(status_code=409, detail="Apply destination DDL before migrating rows.")
    if payload.write_strategy == "UPSERT":
        for table in selected:
            pk = (table.source_primary_key or {}).get("constrained_columns") or []
            included = {
                row.source_column for row in db.query(MigrationColumnMapping).filter_by(
                    plan_table_id=table.id, included=True
                ).all()
            }
            if not pk or any(key not in included for key in pk):
                raise HTTPException(
                    status_code=422,
                    detail=f"UPSERT requires every primary-key column to be included and mapped: {table.source_schema}.{table.source_table}.",
                )
    run = MigrationRun(
        project_id=project_id, owner_id=user.id, plan_id=plan.id,
        batch_size=payload.batch_size, write_strategy=payload.write_strategy,
        max_retries=payload.max_retries, total_tables=len(selected), status="queued",
    )
    db.add(run)
    db.flush()
    db.add(MigrationRunEvent(run_id=run.id, event_type="run_queued", details={"strategy": run.write_strategy, "batch_size": run.batch_size}))
    for table in selected:
        db.add(MigrationRunTable(
            run_id=run.id, plan_table_id=table.id,
            source_schema=table.source_schema, source_table=table.source_table,
            destination_schema=table.destination_schema, destination_table=table.destination_table,
            status="queued",
        ))
    db.commit()
    db.refresh(run)
    return run


@router.get("", response_model=list[MigrationRunResponse])
def list_runs(project_id: uuid.UUID, plan_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_plan(db, user, project_id, plan_id)
    return db.query(MigrationRun).filter_by(project_id=project_id, owner_id=user.id, plan_id=plan_id).order_by(MigrationRun.created_at.desc()).all()


@router.get("/{run_id}", response_model=MigrationRunResponse)
def get_run(project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _owned_run(db, user, project_id, plan_id, run_id)


@router.get("/{run_id}/tables", response_model=list[MigrationRunTableResponse])
def get_run_tables(project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _owned_run(db, user, project_id, plan_id, run_id)
    return db.query(MigrationRunTable).filter_by(run_id=run_id).order_by(MigrationRunTable.source_schema, MigrationRunTable.source_table).all()


@router.get("/{run_id}/errors", response_model=list[MigrationRowErrorResponse])
def get_run_errors(project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _owned_run(db, user, project_id, plan_id, run_id)
    return db.query(MigrationRowError).filter_by(run_id=run_id).order_by(MigrationRowError.created_at).limit(5000).all()


@router.get("/{run_id}/events", response_model=list[MigrationRunEventResponse])
def get_run_events(project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _owned_run(db, user, project_id, plan_id, run_id)
    return db.query(MigrationRunEvent).filter_by(run_id=run_id).order_by(MigrationRunEvent.created_at).limit(10000).all()

@router.get("/{run_id}/metrics")
def get_run_metrics(project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID,
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _owned_run(db, user, project_id, plan_id, run_id)
    run_metric = db.query(MigrationRunMetric).filter_by(run_id=run_id).one_or_none()
    table_metrics = db.query(MigrationTableMetric).filter_by(run_id=run_id).all()
    batches = db.query(MigrationBatchMetric).filter_by(run_id=run_id).order_by(MigrationBatchMetric.created_at.desc()).limit(20).all()
    batches.reverse()
    return {
        "run": ({
            "logical_bytes": run_metric.logical_bytes,
            "rows_fetched": run_metric.rows_fetched,
            "rows_committed": run_metric.rows_committed,
            "batches_committed": run_metric.batches_committed,
            "processing_duration_ms": run_metric.processing_duration_ms,
            "rows_per_second": run_metric.rows_per_second,
            "logical_bytes_per_second": run_metric.logical_bytes_per_second,
            "source_fetch_duration_ms": run_metric.source_fetch_duration_ms,
            "destination_write_duration_ms": run_metric.destination_write_duration_ms,
            "source_network_rtt_ms": run_metric.source_network_rtt_ms,
            "destination_network_rtt_ms": run_metric.destination_network_rtt_ms,
        } if run_metric else None),
        "tables": [{
            "run_table_id": str(item.run_table_id),
            "logical_bytes": item.logical_bytes,
            "rows_fetched": item.rows_fetched,
            "rows_committed": item.rows_committed,
            "batches_committed": item.batches_committed,
            "source_physical_bytes": item.source_physical_bytes,
            "destination_physical_bytes": item.destination_physical_bytes,
            "storage_measured_at": item.storage_measured_at.isoformat() if item.storage_measured_at else None,
        } for item in table_metrics],
        "recent_batches": [{
            "run_table_id": str(item.run_table_id),
            "sequence": item.sequence,
            "logical_bytes": item.logical_bytes,
            "rows_fetched": item.rows_fetched,
            "rows_inserted": item.rows_inserted,
            "rows_updated": item.rows_updated,
            "rows_skipped": item.rows_skipped,
            "rows_failed": item.rows_failed,
            "duration_ms": item.duration_ms,
            "source_fetch_duration_ms": item.source_fetch_duration_ms,
            "destination_write_duration_ms": item.destination_write_duration_ms,
            "network_rtt_ms": item.network_rtt_ms,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        } for item in batches[-20:]],
    }


@router.get("/{run_id}/report")
def get_run_report(project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    run = _owned_run(db, user, project_id, plan_id, run_id)
    tables = db.query(MigrationRunTable).filter_by(run_id=run.id).order_by(MigrationRunTable.source_schema, MigrationRunTable.source_table).all()
    errors = db.query(MigrationRowError).filter_by(run_id=run.id).order_by(MigrationRowError.created_at).limit(5000).all()
    events = db.query(MigrationRunEvent).filter_by(run_id=run.id).order_by(MigrationRunEvent.created_at).limit(10000).all()
    validation_events = db.query(MigrationRunEvent).filter_by(
        run_id=run.id, event_type="validation_finished"
    ).all()
    validation_by_table = {
        str(event.run_table_id): event.details.get("validation")
        for event in validation_events
        if event.run_table_id is not None
        and isinstance(event.details, dict)
        and isinstance(event.details.get("validation"), dict)
    }
    return {
        "run": {
            "id": str(run.id), "status": run.status, "write_strategy": run.write_strategy,
            "batch_size": run.batch_size, "total_rows": run.total_rows,
            "inserted_rows": run.inserted_rows, "updated_rows": run.updated_rows,
            "skipped_rows": run.skipped_rows, "failed_rows": run.failed_rows,
            "validation_status": run.validation_status, "mismatch_rows": run.mismatch_rows,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        },
        "tables": [{
            "source": f"{t.source_schema}.{t.source_table}",
            "destination": f"{t.destination_schema}.{t.destination_table}",
            "status": t.status, "total_rows": t.total_rows,
            "inserted_rows": t.inserted_rows, "updated_rows": t.updated_rows,
            "skipped_rows": t.skipped_rows, "failed_rows": t.failed_rows,
            "validation_status": t.validation_status, "mismatch_rows": t.mismatch_rows,
            "error_message": t.error_message,
            "validation_details": validation_by_table.get(str(t.id)),
        } for t in tables],
        "row_errors": [{
            "table": str(e.run_table_id), "source_key": e.source_key,
            "error_type": e.error_type, "error_message": e.error_message,
            "attempts": e.attempts, "created_at": e.created_at.isoformat(),
            "resolved_at": e.resolved_at.isoformat() if e.resolved_at else None,
        } for e in errors],
        "events": [{
            "event_type": e.event_type, "run_table_id": str(e.run_table_id) if e.run_table_id else None,
            "details": e.details,
            "created_at": e.created_at.isoformat(),
        } for e in events],
    }


@router.get("/{run_id}/report.csv")
def download_run_report_csv(project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    run = _owned_run(db, user, project_id, plan_id, run_id)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "record_type", "source", "destination", "status", "total_rows",
        "inserted_rows", "updated_rows", "skipped_rows", "failed_rows",
        "validation_status", "mismatch_rows", "validation_details",
        "source_key", "error_type", "error_message",
    ])
    writer.writeheader()
    writer.writerow({
        "record_type": "run", "status": run.status, "total_rows": run.total_rows,
        "inserted_rows": run.inserted_rows, "updated_rows": run.updated_rows,
        "skipped_rows": run.skipped_rows, "failed_rows": run.failed_rows,
        "validation_status": run.validation_status, "mismatch_rows": run.mismatch_rows,
    })
    tables = db.query(MigrationRunTable).filter_by(run_id=run.id).order_by(MigrationRunTable.source_schema, MigrationRunTable.source_table).all()
    validation_events = db.query(MigrationRunEvent).filter_by(
        run_id=run.id, event_type="validation_finished"
    ).all()
    validation_by_table = {
        str(event.run_table_id): event.details.get("validation")
        for event in validation_events
        if event.run_table_id is not None
        and isinstance(event.details, dict)
        and isinstance(event.details.get("validation"), dict)
    }
    for table in tables:
        writer.writerow({
            "record_type": "table", "source": f"{table.source_schema}.{table.source_table}",
            "destination": f"{table.destination_schema}.{table.destination_table}",
            "status": table.status, "total_rows": table.total_rows,
            "inserted_rows": table.inserted_rows, "updated_rows": table.updated_rows,
            "skipped_rows": table.skipped_rows, "failed_rows": table.failed_rows,
            "validation_status": table.validation_status, "mismatch_rows": table.mismatch_rows,
            "error_message": table.error_message,
            "validation_details": json.dumps(validation_by_table.get(str(table.id))),
        })
    errors = db.query(MigrationRowError).filter_by(run_id=run.id).order_by(MigrationRowError.created_at).limit(5000).all()
    for item in errors:
        writer.writerow({
            "record_type": "row_error", "source_key": item.source_key,
            "error_type": item.error_type, "error_message": item.error_message,
        })
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="conduit-run-{run.id}.csv"'},
    )


@router.post("/{run_id}/resume", response_model=MigrationRunResponse, status_code=status.HTTP_202_ACCEPTED)
def resume_run(project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    run = _owned_run(db, user, project_id, plan_id, run_id)
    if run.status not in {"failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Only failed or cancelled runs can be resumed. Row-level failures remain quarantined; start a new run after correcting them.")
    run.status = "queued"
    run.finished_at = None
    run.error_message = None
    for table in db.query(MigrationRunTable).filter_by(run_id=run.id).all():
        if table.status != "completed":
            table.status = "queued"
            table.error_message = None
    db.commit()
    db.refresh(run)
    return run



@router.post("/{run_id}/retry-errors", response_model=MigrationRunResponse, status_code=status.HTTP_202_ACCEPTED)
def retry_run_errors(project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    run = _owned_run(db, user, project_id, plan_id, run_id)
    if run.status != "partially_failed" or run.failed_rows == 0:
        raise HTTPException(status_code=409, detail="This run has no quarantined row failures to retry.")
    tables = db.query(MigrationRunTable).filter_by(run_id=run.id).all()
    for table in tables:
        if table.failed_rows:
            table.last_key = None
            table.status = "queued"
            table.inserted_rows = 0
            table.updated_rows = 0
            table.skipped_rows = 0
            table.migrated_rows = 0
            table.failed_rows = 0
            table.retry_count = 0
            table.validation_status = "pending"
            table.mismatch_rows = 0
            table.error_message = None
    run.inserted_rows = sum(table.inserted_rows for table in tables)
    run.updated_rows = sum(table.updated_rows for table in tables)
    run.skipped_rows = sum(table.skipped_rows for table in tables)
    run.migrated_rows = sum(table.migrated_rows for table in tables)
    run.failed_rows = sum(table.failed_rows for table in tables)
    run.mismatch_rows = sum(table.mismatch_rows for table in tables)
    run.completed_tables = sum(1 for table in tables if table.status == "completed")
    run.validation_status = "pending"
    run.status = "queued"
    run.finished_at = None
    run.error_message = None
    db.add(MigrationRunEvent(run_id=run.id, event_type="row_errors_retry_queued", details={"tables_requeued": sum(1 for table in tables if table.status == "queued")}))
    db.commit()
    db.refresh(run)
    return run

@router.post("/{run_id}/cancel", response_model=MigrationRunResponse)
def cancel_run(project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    run = _owned_run(db, user, project_id, plan_id, run_id)
    if run.status == "queued":
        run.status = "cancelled"
        run.finished_at = datetime.now(UTC)
    elif run.status == "running":
        run.status = "cancel_requested"
    db.commit()
    db.refresh(run)
    return run
