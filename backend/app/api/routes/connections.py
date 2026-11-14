import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.connection import (
    ConnectionCreate,
    ConnectionResponse,
    ConnectionTestResponse,
    ConnectionUpdate,
)
from app.services import connection_service

router = APIRouter(prefix="/projects/{project_id}/connections", tags=["Database connections"])


@router.post("", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_connection(
    project_id: uuid.UUID,
    payload: ConnectionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return connection_service.create_connection(db, user, project_id, payload)


@router.get("", response_model=list[ConnectionResponse])
def list_connections(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return connection_service.list_connections(db, user, project_id)


@router.get("/{connection_id}", response_model=ConnectionResponse)
def get_connection(
    project_id: uuid.UUID,
    connection_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return connection_service.get_connection(db, user, project_id, connection_id)


@router.patch("/{connection_id}", response_model=ConnectionResponse)
def update_connection(
    project_id: uuid.UUID,
    connection_id: uuid.UUID,
    payload: ConnectionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    connection = connection_service.get_connection(db, user, project_id, connection_id)
    return connection_service.update_connection(db, connection, payload)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    project_id: uuid.UUID,
    connection_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    connection = connection_service.get_connection(db, user, project_id, connection_id)
    connection_service.delete_connection(db, connection)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{connection_id}/test", response_model=ConnectionTestResponse)
def test_connection(
    project_id: uuid.UUID,
    connection_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    connection = connection_service.get_connection(db, user, project_id, connection_id)
    return connection_service.test_connection(connection)
