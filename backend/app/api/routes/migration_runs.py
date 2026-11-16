import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models.migration_plan import MigrationPlanTable
from app.models.migration_run import MigrationRun, MigrationRunTable
from app.models.user import User
from app.schemas.migration_run import MigrationRunCreate, MigrationRunResponse, MigrationRunTableResponse
from app.services.migration_plan_service import get_plan
from app.services.migration_execution import execute_run

router = APIRouter(prefix="/projects/{project_id}/migration-plans/{plan_id}/runs", tags=["Migration execution"])


def _owned_run(db: Session, user: User, project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID):
    run = db.query(MigrationRun).filter_by(
        id=run_id, project_id=project_id, owner_id=user.id, plan_id=plan_id
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Migration run not found.")
    return run


@router.post("", response_model=MigrationRunResponse, status_code=status.HTTP_201_CREATED)
def start_run(
    project_id: uuid.UUID, plan_id: uuid.UUID, payload: MigrationRunCreate,
    background_tasks: BackgroundTasks, db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = get_plan(db, user, project_id, plan_id)
    if plan.status not in {"ready", "schema_prepared"}:
        raise HTTPException(status_code=409, detail="Validate the plan and prepare destination tables before starting execution.")
    selected = db.query(MigrationPlanTable).filter_by(plan_id=plan.id, selected=True).all()
    if not selected:
        raise HTTPException(status_code=422, detail="Select at least one source table.")
    if any(not table.destination_exists for table in selected):
        raise HTTPException(status_code=409, detail="Apply destination DDL before migrating rows.")
    run = MigrationRun(project_id=project_id, owner_id=user.id, plan_id=plan.id,
                        batch_size=payload.batch_size, total_tables=len(selected), status="queued")
    db.add(run)
    db.flush()
    for table in selected:
        db.add(MigrationRunTable(run_id=run.id, plan_table_id=table.id,
            source_schema=table.source_schema, source_table=table.source_table,
            destination_schema=table.destination_schema, destination_table=table.destination_table,
            status="queued"))
    db.commit()
    db.refresh(run)
    background_tasks.add_task(execute_run, run.id)
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


@router.post("/{run_id}/cancel", response_model=MigrationRunResponse)
def cancel_run(project_id: uuid.UUID, plan_id: uuid.UUID, run_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    run = _owned_run(db, user, project_id, plan_id, run_id)
    if run.status in {"queued", "running"}:
        run.status = "cancelled" if run.status == "queued" else "cancel_requested"
        if run.status == "cancelled":
            from datetime import datetime, timezone
            run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
    return run
