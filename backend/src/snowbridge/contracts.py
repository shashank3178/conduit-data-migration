"""Database-agnostic contracts and invariants for Snowbridge.

Vendor adapters implement these protocols. The domain layer deliberately has no
database-driver dependency and never owns a whole-table result set.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping, Protocol, Sequence


class CapabilityStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    REQUIRES_CONFIGURATION = "requires_configuration"
    REQUIRES_PERMISSION = "requires_permission"


class MappingSafety(StrEnum):
    AUTOMATIC = "automatic"
    WARNING = "warning"
    REQUIRES_TRANSFORM = "requires_transform"
    UNSUPPORTED = "unsupported"


class RunState(StrEnum):
    DRAFT = "draft"
    PREFLIGHT = "preflight"
    SNAPSHOT = "snapshot"
    CDC_CATCHUP = "cdc_catchup"
    RECONCILIATION = "reconciliation"
    CUTOVER_READY = "cutover_ready"
    CUTOVER = "cutover"
    COMPLETED = "completed"
    PAUSED = "paused"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLING_BACK = "rolling_back"


_ALLOWED: dict[RunState, frozenset[RunState]] = {
    RunState.DRAFT: frozenset({RunState.PREFLIGHT, RunState.CANCELLED}),
    RunState.PREFLIGHT: frozenset({RunState.SNAPSHOT, RunState.PAUSED, RunState.FAILED, RunState.CANCELLED}),
    RunState.SNAPSHOT: frozenset({RunState.CDC_CATCHUP, RunState.RECONCILIATION, RunState.PAUSED, RunState.FAILED, RunState.CANCELLED}),
    RunState.CDC_CATCHUP: frozenset({RunState.RECONCILIATION, RunState.PAUSED, RunState.FAILED, RunState.CANCELLED}),
    RunState.RECONCILIATION: frozenset({RunState.CUTOVER_READY, RunState.PAUSED, RunState.FAILED, RunState.CANCELLED}),
    RunState.CUTOVER_READY: frozenset({RunState.CUTOVER, RunState.PAUSED, RunState.FAILED, RunState.CANCELLED}),
    RunState.CUTOVER: frozenset({RunState.COMPLETED, RunState.ROLLING_BACK, RunState.FAILED}),
    RunState.ROLLING_BACK: frozenset({RunState.CANCELLED, RunState.FAILED}),
    RunState.PAUSED: frozenset({RunState.PREFLIGHT, RunState.SNAPSHOT, RunState.CDC_CATCHUP, RunState.RECONCILIATION, RunState.CUTOVER_READY, RunState.CANCELLED, RunState.FAILED}),
    RunState.FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
    RunState.COMPLETED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class Capability:
    name: str
    status: CapabilityStatus
    reason: str
    requirements: tuple[str, ...] = ()
    permission_checks: tuple[str, ...] = ()
    min_version: str | None = None
    max_version: str | None = None

    @property
    def usable(self) -> bool:
        return self.status is CapabilityStatus.AVAILABLE


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    ordinal: int
    native_type: str
    nullable: bool
    precision: int | None = None
    scale: int | None = None
    length: int | None = None
    default_expression: str | None = None
    generated_kind: str | None = None
    identity_kind: str | None = None
    collation: str | None = None
    timezone_aware: bool | None = None


@dataclass(frozen=True, slots=True)
class Key:
    name: str
    columns: tuple[str, ...]
    primary: bool = False
    unique: bool = False


@dataclass(frozen=True, slots=True)
class TableSchema:
    schema_name: str
    table_name: str
    columns: tuple[Column, ...]
    keys: tuple[Key, ...] = ()
    estimated_rows: int | None = None
    partitioned: bool = False


@dataclass(frozen=True, slots=True)
class TypeMapping:
    source_type: str
    target_type: str
    safety: MappingSafety
    rationale: str
    transform_id: str | None = None


@dataclass(frozen=True, slots=True)
class SnapshotHandle:
    snapshot_id: str
    consistency_token: str
    created_at: datetime
    expires_at: datetime | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChunkSpec:
    chunk_id: str
    schema_name: str
    table_name: str
    snapshot_id: str
    predicate: str
    parameters: tuple[Any, ...] = ()
    max_rows: int = 100_000
    max_bytes: int = 64 * 1024 * 1024
    range_spec: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_rows <= 0 or self.max_bytes <= 0:
            raise ValueError("chunk row and byte limits must be positive")
        if not self.chunk_id or not self.snapshot_id:
            raise ValueError("chunk_id and snapshot_id are required")


@dataclass(frozen=True, slots=True)
class SourcePosition:
    kind: str
    value: str
    transaction_id: str | None = None
    transaction_sequence: int | None = None


@dataclass(frozen=True, slots=True)
class CdcEvent:
    event_id: str
    schema_name: str
    table_name: str
    operation: str
    primary_key: Mapping[str, Any]
    before: Mapping[str, Any] | None
    after: Mapping[str, Any] | None
    source_position: SourcePosition
    transaction_end: bool
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class BulkLoadResult:
    committed_rows: int
    committed_bytes: int
    target_commit_token: str | None
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class Checkpoint:
    task_id: str
    chunk_id: str
    snapshot_id: str
    target_commit_token: str
    committed_rows: int
    committed_bytes: int
    source_position: SourcePosition | None = None
    committed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class TaskLease:
    task_id: str
    owner: str
    lease_expires_at: datetime
    attempt: int


@dataclass(frozen=True, slots=True)
class SecretReference:
    provider: str
    secret_id: str
    version: str | None = None


@dataclass(frozen=True, slots=True)
class ConnectionDescriptor:
    connection_id: str
    engine: str
    endpoint_label: str
    secret_ref: SecretReference


def transition_run(current: RunState, target: RunState) -> RunState:
    """Validate and return a legal migration-run state transition."""
    if target not in _ALLOWED[current]:
        raise ValueError(f"illegal migration transition: {current.value} -> {target.value}")
    return target


def assert_checkpoint_after_commit(
    result: BulkLoadResult, checkpoint: Checkpoint
) -> None:
    """Guard checkpoint evidence against a missing or mismatched target commit."""
    if not result.idempotency_key:
        raise ValueError("bulk load must return an idempotency key")
    if checkpoint.target_commit_token != result.target_commit_token:
        raise ValueError("checkpoint target commit token does not match bulk-load result")
    if checkpoint.committed_rows != result.committed_rows:
        raise ValueError("checkpoint row count does not match committed result")
    if checkpoint.committed_bytes != result.committed_bytes:
        raise ValueError("checkpoint byte count does not match committed result")


class SecretProvider(Protocol):
    def resolve(self, reference: SecretReference) -> Mapping[str, str]: ...


class SourceAdapter(Protocol):
    def inspect_capabilities(self) -> Sequence[Capability]: ...
    def discover_schema(self) -> Sequence[TableSchema]: ...
    def begin_consistent_snapshot(self) -> SnapshotHandle: ...
    def read_snapshot_chunk(self, snapshot: SnapshotHandle, chunk: ChunkSpec) -> Any: ...
    def start_cdc(self, snapshot: SnapshotHandle) -> SourcePosition: ...


class TargetAdapter(Protocol):
    def inspect_capabilities(self) -> Sequence[Capability]: ...
    def apply_schema(self, tables: Sequence[TableSchema]) -> None: ...
    def bulk_load(self, table: TableSchema, rows: Any, idempotency_key: str) -> BulkLoadResult: ...
    def apply_changes(self, events: Sequence[CdcEvent], idempotency_key: str) -> BulkLoadResult: ...
    def synchronize_sequences(self, tables: Sequence[TableSchema]) -> None: ...
