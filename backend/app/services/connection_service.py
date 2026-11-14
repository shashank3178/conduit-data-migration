from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
import psycopg
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.connection import DatabaseConnection
from app.models.project import Project
from app.models.user import User
from app.schemas.connection import ConnectionCreate, ConnectionUpdate


def _fernet() -> Fernet:
    key = settings.connection_encryption_key
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection encryption is not configured on the server.",
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server connection-encryption key is invalid.",
        ) from exc


def encrypt_password(password: str) -> str:
    return _fernet().encrypt(password.encode("utf-8")).decode("ascii")


def decrypt_password(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored database credentials could not be decrypted. Check the encryption key.",
        ) from exc


def get_project(db: Session, user: User, project_id) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.owner_id == user.id)
        .first()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def list_connections(db: Session, user: User, project_id) -> list[DatabaseConnection]:
    get_project(db, user, project_id)
    return (
        db.query(DatabaseConnection)
        .filter(
            DatabaseConnection.project_id == project_id,
            DatabaseConnection.owner_id == user.id,
        )
        .order_by(DatabaseConnection.created_at.desc())
        .all()
    )


def get_connection(db: Session, user: User, project_id, connection_id) -> DatabaseConnection:
    connection = (
        db.query(DatabaseConnection)
        .filter(
            DatabaseConnection.id == connection_id,
            DatabaseConnection.project_id == project_id,
            DatabaseConnection.owner_id == user.id,
        )
        .first()
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Database connection not found")
    return connection


def create_connection(
    db: Session, user: User, project_id, payload: ConnectionCreate
) -> DatabaseConnection:
    get_project(db, user, project_id)
    connection = DatabaseConnection(
        project_id=project_id,
        owner_id=user.id,
        name=payload.name,
        role=payload.role,
        host=payload.host,
        port=payload.port,
        database=payload.database,
        username=payload.username,
        password_encrypted=encrypt_password(payload.password),
        sslmode=payload.sslmode,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


def update_connection(
    db: Session, connection: DatabaseConnection, payload: ConnectionUpdate
) -> DatabaseConnection:
    changes = payload.model_dump(exclude_unset=True)
    password = changes.pop("password", None)
    for field, value in changes.items():
        if value is not None:
            setattr(connection, field, value)
    if password is not None:
        connection.password_encrypted = encrypt_password(password)
    db.commit()
    db.refresh(connection)
    return connection


def delete_connection(db: Session, connection: DatabaseConnection) -> None:
    db.delete(connection)
    db.commit()


def test_connection(connection: DatabaseConnection) -> dict:
    password = decrypt_password(connection.password_encrypted)
    try:
        with psycopg.connect(
            host=connection.host,
            port=connection.port,
            dbname=connection.database,
            user=connection.username,
            password=password,
            sslmode=connection.sslmode,
            connect_timeout=5,
            application_name="Conduit connection test",
        ) as conn:
            row = conn.execute(
                "SELECT current_database(), current_user, version()"
            ).fetchone()
        return {
            "success": True,
            "message": f"Successfully connected as {row[1]}.",
            "database": row[0],
            "server_version": row[2].splitlines()[0],
        }
    except psycopg.OperationalError as exc:
        # Do not return the DSN or credentials to the API client.
        message = str(exc).splitlines()[0][:300] or "PostgreSQL connection failed."
        return {"success": False, "message": message}
    except psycopg.Error:
        return {"success": False, "message": "PostgreSQL rejected the connection or test query."}
