import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.migration_plan import (
    ColumnMappingResponse,
    ColumnMappingsUpdate,
    DDLPreviewResponse,
    MigrationPlanCreate,
    MigrationPlanResponse,
    MigrationPlanUpdate,
    PlanTableResponse,
    PlanValidationResponse,
    TableSelectionUpdate,
)
from app.services import migration_plan_service

router = APIRouter(prefix="/projects/{project_id}/migration-plans", tags=["Migration planning"])


@router.post("", response_model=MigrationPlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(
    project_id: uuid.UUID,
    payload: MigrationPlanCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return migration_plan_service.create_plan(db, user, project_id, payload)


@router.get("", response_model=list[MigrationPlanResponse])
def list_plans(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return migration_plan_service.list_plans(db, user, project_id)


@router.get("/{plan_id}", response_model=MigrationPlanResponse)
def get_plan(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return migration_plan_service.get_plan(db, user, project_id, plan_id)


@router.patch("/{plan_id}", response_model=MigrationPlanResponse)
def update_plan(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: MigrationPlanUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = migration_plan_service.get_plan(db, user, project_id, plan_id)
    return migration_plan_service.update_plan(db, plan, payload)


@router.get("/{plan_id}/metrics")
def get_plan_metrics(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = migration_plan_service.get_plan(db, user, project_id, plan_id)
    return migration_plan_service.get_plan_metrics(db, plan)


@router.get("/{plan_id}/tables", response_model=list[PlanTableResponse])
def list_tables(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = migration_plan_service.get_plan(db, user, project_id, plan_id)
    return migration_plan_service.list_plan_tables(db, plan)


@router.put("/{plan_id}/tables/selection", response_model=list[PlanTableResponse])
def update_selection(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: TableSelectionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = migration_plan_service.get_plan(db, user, project_id, plan_id)
    return migration_plan_service.update_table_selection(db, plan, payload)


@router.post("/{plan_id}/mappings/suggest", response_model=list[PlanTableResponse])
def suggest_mappings(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = migration_plan_service.get_plan(db, user, project_id, plan_id)
    return migration_plan_service.suggest_mappings(db, plan)


@router.put("/{plan_id}/tables/{table_id}/mappings", response_model=list[ColumnMappingResponse])
def update_mappings(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    table_id: uuid.UUID,
    payload: ColumnMappingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = migration_plan_service.get_plan(db, user, project_id, plan_id)
    return migration_plan_service.update_column_mappings(db, plan, table_id, payload)


@router.post("/{plan_id}/validate", response_model=PlanValidationResponse)
def validate_plan(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = migration_plan_service.get_plan(db, user, project_id, plan_id)
    return migration_plan_service.validate_and_update_plan(db, plan)


@router.get("/{plan_id}/ddl", response_model=DDLPreviewResponse)
def preview_ddl(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = migration_plan_service.get_plan(db, user, project_id, plan_id)
    return migration_plan_service.preview_ddl(db, plan, user, project_id)


@router.post("/{plan_id}/ddl/apply")
def apply_ddl(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = migration_plan_service.get_plan(db, user, project_id, plan_id)
    return migration_plan_service.apply_ddl(db, user, project_id, plan)
