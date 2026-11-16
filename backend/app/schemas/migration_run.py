import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RunStatus = Literal["queued", "running", "completed", "failed", "cancel_requested", "cancelled", "partially_failed"]


class MigrationRunCreate(BaseModel):
    batch_size: int = Field(default=1000, ge=100, le=10000)


class MigrationRunTableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    plan_table_id: uuid.UUID
    source_schema: str
    source_table: str
    destination_schema: str
    destination_table: str
    status: str
    total_rows: int
    migrated_rows: int
    failed_rows: int
    error_message: str | None


class MigrationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    plan_id: uuid.UUID
    status: RunStatus
    batch_size: int
    total_tables: int
    completed_tables: int
    total_rows: int
    migrated_rows: int
    failed_rows: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
