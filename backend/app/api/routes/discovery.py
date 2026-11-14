import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.discovery import DiscoveryRunResponse, DiscoveryStatusResponse, SchemaResponse, TableSummaryResponse, TableDetailResponse
from app.services import discovery_service

router = APIRouter(prefix="/projects/{project_id}/connections/{connection_id}", tags=["Database discovery"])


def _run_response(snapshot, message="Database discovery completed successfully."):
    return {"snapshot_id": snapshot.id, "connection_id": snapshot.connection_id, "status": snapshot.status,
        "database_name": snapshot.database_name, "server_version": snapshot.server_version,
        "schema_count": snapshot.schema_count, "table_count": snapshot.table_count,
        "discovered_at": snapshot.discovered_at, "message": message}


@router.post("/discover", response_model=DiscoveryRunResponse)
def run_discovery(project_id: uuid.UUID, connection_id: uuid.UUID,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _run_response(discovery_service.discover(db, user, project_id, connection_id))


@router.get("/discovery", response_model=DiscoveryStatusResponse)
def discovery_status(project_id: uuid.UUID, connection_id: uuid.UUID,
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    snapshot = discovery_service.get_snapshot(db, user, project_id, connection_id)
    result = _run_response(snapshot, "Latest discovery snapshot.")
    result["error_message"] = snapshot.error_message
    return result


@router.get("/schemas", response_model=list[SchemaResponse])
def discovered_schemas(project_id: uuid.UUID, connection_id: uuid.UUID,
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return discovery_service.list_schemas(db, user, project_id, connection_id)


@router.get("/tables", response_model=list[TableSummaryResponse])
def discovered_tables(project_id: uuid.UUID, connection_id: uuid.UUID,
                      schema: str | None = Query(default=None),
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return discovery_service.list_tables(db, user, project_id, connection_id, schema)


@router.get("/tables/{table_id}", response_model=TableDetailResponse)
def discovered_table(project_id: uuid.UUID, connection_id: uuid.UUID, table_id: uuid.UUID,
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return discovery_service.get_table(db, user, project_id, connection_id, table_id)
