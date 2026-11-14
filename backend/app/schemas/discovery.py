import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


DiscoveryStatus = Literal["pending", "running", "completed", "failed"]


class DiscoveryRunResponse(BaseModel):
    snapshot_id: uuid.UUID
    connection_id: uuid.UUID
    status: DiscoveryStatus
    database_name: str
    server_version: str | None
    schema_count: int
    table_count: int
    discovered_at: datetime | None
    message: str


class DiscoveryStatusResponse(DiscoveryRunResponse):
    error_message: str | None = None


class SchemaResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_system: bool
    table_count: int


class TableSummaryResponse(BaseModel):
    id: uuid.UUID
    schema_name: str
    name: str
    table_type: str
    estimated_rows: int | None


class TableDetailResponse(TableSummaryResponse):
    columns: list[dict[str, Any]]
    primary_key: dict[str, Any]
    foreign_keys: list[dict[str, Any]]
    unique_constraints: list[dict[str, Any]]
    check_constraints: list[dict[str, Any]]
    indexes: list[dict[str, Any]]
    comment: str | None

    model_config = ConfigDict(from_attributes=True)
