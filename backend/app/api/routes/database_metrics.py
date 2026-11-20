"""Database storage snapshots scoped to the authenticated owner."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models.migration_metrics import MigrationDatabaseMetric
from app.models.migration_run import MigrationRun
from app.models.user import User

router = APIRouter(prefix="/analytics", tags=["Database analytics"])


@router.get("/databases")
def analytics_databases(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    snapshots = db.query(MigrationDatabaseMetric).join(
        MigrationRun, MigrationRun.id == MigrationDatabaseMetric.run_id
    ).filter(MigrationRun.owner_id == user.id).order_by(
        MigrationDatabaseMetric.captured_at.desc()
    ).limit(100).all()
    return [{
        "run_id": str(item.run_id), "connection_id": str(item.connection_id),
        "role": item.role, "database_name": item.database_name,
        "physical_bytes": item.physical_bytes, "measurement_kind": item.measurement_kind,
        "captured_at": item.captured_at,
    } for item in snapshots]
