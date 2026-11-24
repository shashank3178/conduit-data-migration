"""Unified schema inventory, capability report, type mapping and estimates."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
from typing import Any,Sequence
from snowbridge.contracts import Capability,MappingSafety,TableSchema
from snowbridge.type_mapping import map_type,normalize_engine

@dataclass(frozen=True,slots=True)
class ColumnMapping:
    schema_name:str
    table_name:str
    column_name:str
    mapping:Any
@dataclass(frozen=True,slots=True)
class MigrationEstimate:
    table_count:int
    column_count:int
    estimated_rows:int
    estimated_bytes:int
    unknown_row_tables:tuple[str,...]
    unknown_size_tables:tuple[str,...]
    confidence:str
    assumptions:tuple[str,...]
    estimated_duration_seconds:float|None
@dataclass(frozen=True,slots=True)
class SchemaInventory:
    engine:str
    captured_at:datetime
    tables:tuple[TableSchema,...]
    capabilities:tuple[Capability,...]
    mappings:tuple[ColumnMapping,...]
    unsupported_mappings:tuple[ColumnMapping,...]
    warnings:tuple[str,...]
    estimate:MigrationEstimate

def estimate_migration(tables:Sequence[TableSchema],effective_bytes_per_second:float|None=None)->MigrationEstimate:
    if effective_bytes_per_second is not None and effective_bytes_per_second <= 0:
        raise ValueError("effective_bytes_per_second must be positive")
    rows=size=0; unknown_rows=[]; unknown_size=[]
    for t in tables:
        name=f"{t.schema_name}.{t.table_name}"
        if t.estimated_rows is None:unknown_rows.append(name)
        else:rows+=max(0,t.estimated_rows)
        if t.estimated_bytes is None:unknown_size.append(name)
        else:size+=max(0,t.estimated_bytes)
    missing=len(unknown_rows)+len(unknown_size)
    confidence="high" if not missing else "medium" if missing<=max(1,len(tables)//4) else "low"
    return MigrationEstimate(len(tables),sum(len(t.columns) for t in tables),rows,size,
        tuple(unknown_rows),tuple(unknown_size),confidence,
        ("Catalog row/byte estimates are not snapshot-exact counts.",
         "InnoDB TABLE_ROWS and PostgreSQL reltuples are approximate.",
         "Oracle NUM_ROWS/blocks depend on optimizer statistics freshness.",
         "LOB payload, compression, target indexes and conversion overhead may change final size."),
        size / effective_bytes_per_second if effective_bytes_per_second is not None and not unknown_size else None)

def discover_inventory(adapter:Any,source_engine:str,target_engine:str|None=None,
                       schemas:Sequence[str]|None=None)->SchemaInventory:
    engine=normalize_engine(source_engine)
    caps=tuple(adapter.inspect_capabilities()); tables=tuple(adapter.discover_schema(schemas))
    mappings = []
    unsupported = []
    warnings = [
        "Inventory scope is base tables, columns and primary/usable unique keys; views, foreign keys, checks, standalone indexes, sequences, triggers, routines and grants are not yet inventoried."
    ]
    if target_engine:
        target=normalize_engine(target_engine)
        for table in tables:
            for col in table.columns:
                result=map_type(engine,target,col.native_type,col.precision,col.scale,col.length,col.timezone_aware)
                item=ColumnMapping(table.schema_name,table.table_name,col.name,result);mappings.append(item)
                if result.safety in {MappingSafety.UNSUPPORTED,MappingSafety.REQUIRES_TRANSFORM}:unsupported.append(item)
                elif result.safety is MappingSafety.WARNING:warnings.append(f"{table.schema_name}.{table.table_name}.{col.name}: {result.rationale}")
    inventory=SchemaInventory(engine,datetime.now(timezone.utc),tables,caps,tuple(mappings),
        tuple(unsupported),tuple(warnings),estimate_migration(tables))
    assert_inventory_complete(inventory)
    return inventory

def assert_inventory_complete(inventory:SchemaInventory)->None:
    issues=[]
    for t in inventory.tables:
        name=f"{t.schema_name}.{t.table_name}"
        if not t.columns:issues.append(f"{name}: no columns returned")
        ordinals=[c.ordinal for c in t.columns]
        if ordinals!=sorted(ordinals) or len(ordinals)!=len(set(ordinals)):issues.append(f"{name}: invalid column ordinals")
        names={c.name for c in t.columns}
        for key in t.keys:
            if not key.columns or any(c not in names for c in key.columns):issues.append(f"{name}: key {key.name} references missing columns")
    if issues:raise ValueError("incomplete schema inventory: "+"; ".join(issues))
