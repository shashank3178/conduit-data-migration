import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConnectionRole = Literal["source", "destination"]
SSLMode = Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]


class ConnectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: ConnectionRole
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)
    sslmode: SSLMode = "prefer"


class ConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: ConnectionRole | None = None
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str | None = Field(default=None, min_length=1, max_length=128)
    username: str | None = Field(default=None, min_length=1, max_length=128)
    password: str | None = Field(default=None, min_length=1, max_length=1024)
    sslmode: SSLMode | None = None


class ConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    role: ConnectionRole
    host: str
    port: int
    database: str
    username: str
    sslmode: SSLMode
    created_at: datetime
    updated_at: datetime
    has_password: bool = True


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
    database: str | None = None
    server_version: str | None = None
