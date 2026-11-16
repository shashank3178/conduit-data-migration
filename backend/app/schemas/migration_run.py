import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RunStatus = Literal["queued", "running", "completed", "failed", "cancel_requested", "cancelled", "partially_failed"]
WriteStrategy = Literal["INSERT_ONLY", "UPSERT"]


class MigrationRunCreate(BaseModel):
    batch_size: int = Field(default=1000, ge=100, le=10000)
    write_strategy: WriteStrategy = "INSERT_ONLY"
    max_retries: int = Field(default=3, ge=0, le=10)


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
    inserted_rows: int
    updated_rows: int
    skipped_rows: int
    failed_rows: int
    retry_count: int
    validation_status: str
    mismatch_rows: int
    error_message: str | None


class MigrationRowErrorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    run_table_id: uuid.UUID
    source_key: dict
    error_type: str
    error_message: str
    attempts: int
    created_at: datetime
    resolved_at: datetime | None


class MigrationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    plan_id: uuid.UUID
    status: RunStatus
    batch_size: int
    write_strategy: WriteStrategy
    max_retries: int
    total_tables: int
    completed_tables: int
    total_rows: int
    migrated_rows: int
    inserted_rows: int
    updated_rows: int
    skipped_rows: int
    failed_rows: int
    validation_status: str
    mismatch_rows: int
    heartbeat_at: datetime | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
