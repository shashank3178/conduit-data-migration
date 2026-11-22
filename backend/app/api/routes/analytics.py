"""Authenticated workspace and per-run migration analytics."""
import json
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.db.session import SessionLocal
from app.models.migration_metrics import (
    MigrationBatchMetric,
    MigrationDatabaseMetric,
    MigrationRunMetric,
    MigrationTableMetric,
)
from app.models.migration_run import MigrationRun, MigrationRunEvent, MigrationRunTable
from app.models.user import User

router = APIRouter(prefix="/analytics", tags=["Migration analytics"])


@router.get("/overview")
def analytics_overview(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    base = db.query(MigrationRun).filter(MigrationRun.owner_id == user.id)
    total_runs = base.count()
    active_runs = base.filter(MigrationRun.status.in_(["queued", "running", "cancel_requested"])).count()
    completed_runs = base.filter(MigrationRun.status == "completed").count()
    failed_runs = base.filter(MigrationRun.status.in_(["failed", "partially_failed"])).count()
    totals = db.query(
        func.coalesce(func.sum(MigrationRun.inserted_rows + MigrationRun.updated_rows), 0),
        func.coalesce(func.sum(MigrationRun.inserted_rows), 0),
        func.coalesce(func.sum(MigrationRun.updated_rows), 0),
        func.coalesce(func.sum(MigrationRun.skipped_rows), 0),
        func.coalesce(func.sum(MigrationRun.failed_rows), 0),
    ).filter(MigrationRun.owner_id == user.id).one()
    metrics_runs_count = db.query(func.count(MigrationRunMetric.id)).join(
        MigrationRun, MigrationRun.id == MigrationRunMetric.run_id
    ).filter(MigrationRun.owner_id == user.id).scalar() or 0
    metric_totals = db.query(
        func.coalesce(func.sum(MigrationRunMetric.logical_bytes), 0),
        func.coalesce(func.sum(MigrationRunMetric.rows_fetched), 0),
        func.coalesce(func.sum(MigrationRunMetric.batches_committed), 0),
        func.coalesce(func.avg(MigrationRunMetric.rows_per_second), 0),
        func.coalesce(func.avg(MigrationRunMetric.logical_bytes_per_second), 0),
    ).join(MigrationRun, MigrationRun.id == MigrationRunMetric.run_id).filter(
        MigrationRun.owner_id == user.id
    ).one()
    recent = base.order_by(MigrationRun.created_at.desc()).limit(12).all()
    recent_ids = [item.id for item in recent]
    metrics = {
        item.run_id: item for item in db.query(MigrationRunMetric).filter(
            MigrationRunMetric.run_id.in_(recent_ids)
        ).all()
    } if recent_ids else {}
    return {
        "summary": {
            "total_runs": total_runs,
            "active_runs": active_runs,
            "completed_runs": completed_runs,
            "failed_runs": failed_runs,
            "rows_committed": int(totals[0]),
            "rows_inserted": int(totals[1]),
            "rows_updated": int(totals[2]),
            "rows_skipped": int(totals[3]),
            "rows_failed": int(totals[4]),
            "metrics_runs_count": int(metrics_runs_count),
            "logical_bytes": int(metric_totals[0]),
            "rows_fetched": int(metric_totals[1]),
            "batches_committed": int(metric_totals[2]),
            "average_rows_per_second": round(float(metric_totals[3]), 2),
            "average_logical_bytes_per_second": round(float(metric_totals[4]), 2),
        },
        "recent_runs": [{
            "id": str(item.id),
            "project_id": str(item.project_id),
            "plan_id": str(item.plan_id),
            "status": item.status,
            "created_at": item.created_at,
            "started_at": item.started_at,
            "finished_at": item.finished_at,
            "total_rows": item.total_rows,
            "migrated_rows": item.migrated_rows,
            "inserted_rows": item.inserted_rows,
            "updated_rows": item.updated_rows,
            "skipped_rows": item.skipped_rows,
            "failed_rows": item.failed_rows,
            "worker_id": item.worker_id,
            "logical_bytes": int(metrics[item.id].logical_bytes) if item.id in metrics else None,
            "rows_per_second": round(metrics[item.id].rows_per_second, 2) if item.id in metrics else None,
        } for item in recent],
    }


@router.get("/runs/{run_id}")
def analytics_run_detail(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = db.query(MigrationRun).filter_by(id=run_id, owner_id=user.id).one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Migration run not found.")
    run_metric = db.query(MigrationRunMetric).filter_by(run_id=run.id).one_or_none()
    tables = db.query(MigrationRunTable).filter_by(run_id=run.id).order_by(
        MigrationRunTable.source_schema, MigrationRunTable.source_table
    ).all()
    table_metrics = {
        item.run_table_id: item for item in db.query(MigrationTableMetric).filter_by(run_id=run.id).all()
    }
    batches = db.query(MigrationBatchMetric).filter_by(run_id=run.id).order_by(
        MigrationBatchMetric.created_at.desc()
    ).limit(100).all()
    validation_events = db.query(MigrationRunEvent).filter_by(run_id=run.id, event_type="validation_finished").all()
    validation_by_table = {
        str(event.run_table_id): event.details.get("validation")
        for event in validation_events
        if event.run_table_id is not None and isinstance(event.details, dict)
        and isinstance(event.details.get("validation"), dict)
    }
    databases = db.query(MigrationDatabaseMetric).filter_by(run_id=run.id).order_by(
        MigrationDatabaseMetric.captured_at.desc()
    ).limit(20).all()
    return {
        "run": {
            "id": str(run.id), "status": run.status, "worker_id": run.worker_id,
            "batch_size": run.batch_size, "write_strategy": run.write_strategy,
            "total_rows": run.total_rows, "migrated_rows": run.migrated_rows,
            "inserted_rows": run.inserted_rows, "updated_rows": run.updated_rows,
            "skipped_rows": run.skipped_rows, "failed_rows": run.failed_rows,
            "validation_status": run.validation_status, "mismatch_rows": run.mismatch_rows,
            "heartbeat_at": run.heartbeat_at, "started_at": run.started_at,
            "finished_at": run.finished_at, "error_message": run.error_message,
        },
        "metrics": None if run_metric is None else {
            "rows_fetched": run_metric.rows_fetched,
            "rows_committed": run_metric.rows_committed,
            "batches_committed": run_metric.batches_committed,
            "logical_bytes": run_metric.logical_bytes,
            "processing_duration_ms": run_metric.processing_duration_ms,
            "rows_per_second": run_metric.rows_per_second,
            "logical_bytes_per_second": run_metric.logical_bytes_per_second,
            "source_fetch_duration_ms": run_metric.source_fetch_duration_ms,
            "destination_write_duration_ms": run_metric.destination_write_duration_ms,
            "source_network_rtt_ms": run_metric.source_network_rtt_ms,
            "destination_network_rtt_ms": run_metric.destination_network_rtt_ms,
        },
        "tables": [{
            "id": str(item.id), "source": f"{item.source_schema}.{item.source_table}",
            "destination": f"{item.destination_schema}.{item.destination_table}",
            "status": item.status, "total_rows": item.total_rows,
            "inserted_rows": item.inserted_rows, "updated_rows": item.updated_rows,
            "skipped_rows": item.skipped_rows, "failed_rows": item.failed_rows,
            "validation_status": item.validation_status, "mismatch_rows": item.mismatch_rows,
            "validation_details": validation_by_table.get(str(item.id)),
            "metrics": None if item.id not in table_metrics else {
                "rows_fetched": table_metrics[item.id].rows_fetched,
                "rows_committed": table_metrics[item.id].rows_committed,
                "batches_committed": table_metrics[item.id].batches_committed,
                "logical_bytes": table_metrics[item.id].logical_bytes,
                "source_physical_bytes": table_metrics[item.id].source_physical_bytes,
                "destination_physical_bytes": table_metrics[item.id].destination_physical_bytes,
                "storage_measured_at": table_metrics[item.id].storage_measured_at,
            },
        } for item in tables],
        "batches": [{
            "id": str(item.id), "run_table_id": str(item.run_table_id),
            "sequence": item.sequence, "rows_fetched": item.rows_fetched,
            "rows_inserted": item.rows_inserted, "rows_updated": item.rows_updated,
            "rows_skipped": item.rows_skipped, "rows_failed": item.rows_failed,
            "logical_bytes": item.logical_bytes, "duration_ms": item.duration_ms,
            "source_fetch_duration_ms": item.source_fetch_duration_ms,
            "destination_write_duration_ms": item.destination_write_duration_ms,
            "network_rtt_ms": item.network_rtt_ms,
            "checkpoint_start": item.checkpoint_start, "checkpoint_end": item.checkpoint_end,
            "created_at": item.created_at,
        } for item in batches],
        "databases": [{
            "role": item.role, "database_name": item.database_name,
            "physical_bytes": item.physical_bytes, "measurement_kind": item.measurement_kind,
            "captured_at": item.captured_at,
        } for item in databases],
    }


@router.get("/runs/{run_id}/stream")
def stream_run_events(
    run_id: uuid.UUID,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = db.query(MigrationRun).filter_by(id=run_id, owner_id=user.id).one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Migration run not found.")

    cursor_time = run.created_at
    cursor_id = uuid.UUID(int=0)
    if last_event_id:
        try:
            timestamp, event_id = last_event_id.split("|", 1)
            cursor_time = datetime.fromisoformat(timestamp)
            cursor_id = uuid.UUID(event_id)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="Invalid Last-Event-ID header.") from exc

    def event_stream():
        nonlocal cursor_time, cursor_id
        terminal = {"completed", "failed", "partially_failed", "cancelled"}
        while True:
            with SessionLocal() as stream_db:
                current = stream_db.query(MigrationRun).filter_by(
                    id=run_id, owner_id=user.id
                ).one_or_none()
                if current is None:
                    return
                events = stream_db.query(MigrationRunEvent).filter(
                    MigrationRunEvent.run_id == run_id,
                    or_(
                        MigrationRunEvent.created_at > cursor_time,
                        and_(
                            MigrationRunEvent.created_at == cursor_time,
                            MigrationRunEvent.id > cursor_id,
                        ),
                    ),
                ).order_by(
                    MigrationRunEvent.created_at, MigrationRunEvent.id
                ).limit(100).all()
                for event in events:
                    cursor_time = event.created_at
                    cursor_id = event.id
                    event_id = cursor_time.isoformat() + "|" + str(cursor_id)
                    payload = {
                        "id": str(event.id),
                        "event_type": event.event_type,
                        "details": event.details,
                        "created_at": event.created_at.isoformat(),
                    }
                    yield "id: " + event_id + "\nevent: migration\ndata: " + json.dumps(payload, default=str) + "\n\n"
                if current.status in terminal and not events:
                    yield "event: terminal\ndata: " + json.dumps({"status": current.status}) + "\n\n"
                    return
            yield ": keep-alive\n\n"
            time.sleep(2)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
