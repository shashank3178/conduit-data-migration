import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PlanStatus = Literal["draft", "ready", "schema_prepared"]


class MigrationPlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    source_connection_id: uuid.UUID
    destination_connection_id: uuid.UUID
    create_schemas: bool = True


class MigrationPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    create_schemas: bool | None = None


class MigrationPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    source_connection_id: uuid.UUID
    destination_connection_id: uuid.UUID
    source_snapshot_id: uuid.UUID
    destination_snapshot_id: uuid.UUID
    status: PlanStatus
    create_schemas: bool
    created_at: datetime
    updated_at: datetime


class TableSelectionItem(BaseModel):
    table_id: uuid.UUID
    selected: bool
    destination_schema: str = Field(min_length=1, max_length=128)
    destination_table: str = Field(min_length=1, max_length=128)


class TableSelectionUpdate(BaseModel):
    tables: list[TableSelectionItem] = Field(min_length=1, max_length=1000)


class ColumnMappingInput(BaseModel):
    source_column: str = Field(min_length=1, max_length=128)
    destination_column: str | None = Field(default=None, max_length=128)
    destination_type: str | None = Field(default=None, max_length=255)
    included: bool = True


class ColumnMappingsUpdate(BaseModel):
    mappings: list[ColumnMappingInput] = Field(max_length=1000)


class ColumnMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_table_id: uuid.UUID
    source_column: str
    destination_column: str | None
    source_type: str
    destination_type: str | None
    included: bool
    compatible: bool
    match_strategy: str


class PlanTableResponse(BaseModel):
    id: uuid.UUID
    source_schema: str
    source_table: str
    source_table_type: str
    destination_schema: str
    destination_table: str
    selected: bool
    destination_exists: bool
    estimated_rows: int | None
    column_count: int
    mappings: list[ColumnMappingResponse]


class PlanValidationResponse(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]
    selected_table_count: int
    mapped_column_count: int


class DDLPreviewResponse(BaseModel):
    statements: list[str]
    warnings: list[str]
    tables_to_create: int
    schemas_to_create: list[str]
