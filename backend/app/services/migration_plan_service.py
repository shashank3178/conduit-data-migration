import uuid

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.discovery import DiscoveredSchema, DiscoveredTable, DiscoverySnapshot
from app.models.migration_plan import MigrationColumnMapping, MigrationPlan, MigrationPlanTable
from app.models.user import User
from app.schemas.migration_plan import (
    ColumnMappingsUpdate,
    MigrationPlanCreate,
    MigrationPlanUpdate,
    TableSelectionUpdate,
)
from app.services import connection_service, project_service
from app.services.migration_ddl import build_ddl, normalize_pg_type, types_compatible


def _columns_by_name(columns: list[dict]) -> dict[str, dict]:
    return {column.get("name"): column for column in columns if column.get("name")}


def _suggest_column_mappings(db: Session, plan_table: MigrationPlanTable) -> None:
    destination_columns = _columns_by_name(plan_table.destination_columns or [])
    for source in plan_table.source_columns or []:
        source_name = source.get("name")
        source_type = source.get("type") or "TEXT"
        target = destination_columns.get(source_name)
        if plan_table.destination_exists:
            target_name = target.get("name") if target else None
            target_type = target.get("type") if target else None
            strategy = "exact_name" if target else "unmapped"
        else:
            target_name = source_name
            target_type = source_type
            strategy = "same_name_new_table"
        db.add(
            MigrationColumnMapping(
                plan_table_id=plan_table.id,
                source_column=source_name,
                destination_column=target_name,
                source_type=str(source_type),
                destination_type=str(target_type or source_type) if target_name else None,
                included=bool(target_name),
                compatible=types_compatible(str(source_type), str(target_type or source_type)),
                match_strategy=strategy,
            )
        )


def get_plan(db: Session, user: User, project_id: uuid.UUID, plan_id: uuid.UUID) -> MigrationPlan:
    plan = (
        db.query(MigrationPlan)
        .filter(
            MigrationPlan.id == plan_id,
            MigrationPlan.project_id == project_id,
            MigrationPlan.owner_id == user.id,
        )
        .first()
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Migration plan not found.")
    return plan


def create_plan(db: Session, user: User, project_id: uuid.UUID, payload: MigrationPlanCreate) -> MigrationPlan:
    project_service.get_project(db, user, project_id)
    if payload.source_connection_id == payload.destination_connection_id:
        raise HTTPException(status_code=422, detail="Source and destination connections must be different.")

    source_connection = connection_service.get_connection(
        db, user, project_id, payload.source_connection_id
    )
    destination_connection = connection_service.get_connection(
        db, user, project_id, payload.destination_connection_id
    )
    if source_connection.role != "source" or destination_connection.role != "destination":
        raise HTTPException(
            status_code=422,
            detail="Select a connection registered with the source role and one with the destination role.",
        )

    source_snapshot = (
        db.query(DiscoverySnapshot)
        .filter_by(project_id=project_id, connection_id=source_connection.id, status="completed")
        .first()
    )
    destination_snapshot = (
        db.query(DiscoverySnapshot)
        .filter_by(project_id=project_id, connection_id=destination_connection.id, status="completed")
        .first()
    )
    if source_snapshot is None or destination_snapshot is None:
        raise HTTPException(
            status_code=409,
            detail="Run and complete discovery for both source and destination connections before creating a migration plan.",
        )

    plan = MigrationPlan(
        project_id=project_id,
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
        source_connection_id=source_connection.id,
        destination_connection_id=destination_connection.id,
        source_snapshot_id=source_snapshot.id,
        destination_snapshot_id=destination_snapshot.id,
        create_schemas=payload.create_schemas,
        status="draft",
    )
    db.add(plan)
    db.flush()

    source_rows = (
        db.query(DiscoveredTable, DiscoveredSchema.name)
        .join(DiscoveredSchema, DiscoveredTable.schema_id == DiscoveredSchema.id)
        .filter(DiscoveredSchema.snapshot_id == source_snapshot.id, DiscoveredSchema.is_system.is_(False))
        .order_by(DiscoveredSchema.name, DiscoveredTable.name)
        .all()
    )
    destination_rows = (
        db.query(DiscoveredTable, DiscoveredSchema.name)
        .join(DiscoveredSchema, DiscoveredTable.schema_id == DiscoveredSchema.id)
        .filter(DiscoveredSchema.snapshot_id == destination_snapshot.id, DiscoveredSchema.is_system.is_(False))
        .all()
    )
    destination_by_name = {(schema, table.name): table for table, schema in destination_rows}

    for source_table, source_schema in source_rows:
        destination_table = destination_by_name.get((source_schema, source_table.name))
        row = MigrationPlanTable(
            plan_id=plan.id,
            source_table_id=source_table.id,
            destination_table_id=destination_table.id if destination_table else None,
            source_schema=source_schema,
            source_table=source_table.name,
            source_table_type=source_table.table_type,
            destination_schema=source_schema,
            destination_table=source_table.name,
            selected=False,
            destination_exists=destination_table is not None,
            estimated_rows=source_table.estimated_rows,
            source_columns=source_table.columns or [],
            destination_columns=destination_table.columns if destination_table else [],
            source_primary_key=source_table.primary_key or {},
        )
        db.add(row)
        db.flush()
        _suggest_column_mappings(db, row)

    db.commit()
    db.refresh(plan)
    return plan


def list_plans(db: Session, user: User, project_id: uuid.UUID):
    project_service.get_project(db, user, project_id)
    return (
        db.query(MigrationPlan)
        .filter_by(project_id=project_id, owner_id=user.id)
        .order_by(MigrationPlan.created_at.desc())
        .all()
    )


def update_plan(db: Session, plan: MigrationPlan, payload: MigrationPlanUpdate):
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(plan, field, value)
    if plan.status != "schema_prepared":
        plan.status = "draft"
    db.commit()
    db.refresh(plan)
    return plan


def list_plan_tables(db: Session, plan: MigrationPlan):
    rows = (
        db.query(MigrationPlanTable)
        .filter_by(plan_id=plan.id)
        .order_by(MigrationPlanTable.source_schema, MigrationPlanTable.source_table)
        .all()
    )
    result = []
    for row in rows:
        mappings = (
            db.query(MigrationColumnMapping)
            .filter_by(plan_table_id=row.id)
            .order_by(MigrationColumnMapping.source_column)
            .all()
        )
        result.append(
            {
                "id": row.id,
                "source_schema": row.source_schema,
                "source_table": row.source_table,
                "source_table_type": row.source_table_type,
                "destination_schema": row.destination_schema,
                "destination_table": row.destination_table,
                "selected": row.selected,
                "destination_exists": row.destination_exists,
                "estimated_rows": row.estimated_rows,
                "column_count": len(row.source_columns or []),
                "mappings": mappings,
            }
        )
    return result


def update_table_selection(db: Session, plan: MigrationPlan, payload: TableSelectionUpdate):
    ids = [item.table_id for item in payload.tables]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="A table may appear only once in a selection update.")
    rows = (
        db.query(MigrationPlanTable)
        .filter(MigrationPlanTable.plan_id == plan.id, MigrationPlanTable.id.in_(ids))
        .all()
    )
    if len(rows) != len(ids):
        raise HTTPException(status_code=404, detail="One or more table selections do not belong to this plan.")

    destination_rows = (
        db.query(DiscoveredTable, DiscoveredSchema.name)
        .join(DiscoveredSchema, DiscoveredTable.schema_id == DiscoveredSchema.id)
        .filter(DiscoveredSchema.snapshot_id == plan.destination_snapshot_id)
        .all()
    )
    destination_by_name = {
        (schema, table.name): table for table, schema in destination_rows
    }
    updates = {item.table_id: item for item in payload.tables}

    for row in rows:
        item = updates[row.id]
        if item.selected and row.source_table_type != "table":
            raise HTTPException(
                status_code=422,
                detail=f"{row.source_schema}.{row.source_table} is not a regular table and cannot be selected.",
            )
        target = destination_by_name.get((item.destination_schema, item.destination_table))
        if target is not None and target.table_type != "table":
            raise HTTPException(
                status_code=422,
                detail=f"Destination {item.destination_schema}.{item.destination_table} is not a regular table.",
            )

        target_changed = (
            row.destination_schema != item.destination_schema
            or row.destination_table != item.destination_table
        )
        # Preserve a table created by this plan even if the original destination
        # discovery snapshot predates the CREATE TABLE operation.
        already_prepared_target = target is None and not target_changed and row.destination_exists
        target_state_changed = row.destination_exists != (target is not None) and not already_prepared_target
        target_id_changed = target is not None and row.destination_table_id != target.id

        row.selected = item.selected
        row.destination_schema = item.destination_schema
        row.destination_table = item.destination_table
        if target is not None:
            row.destination_exists = True
            row.destination_table_id = target.id
            row.destination_columns = target.columns or []
        elif not already_prepared_target:
            row.destination_exists = False
            row.destination_table_id = None
            row.destination_columns = []

        if target_changed or target_state_changed or target_id_changed:
            db.query(MigrationColumnMapping).filter_by(plan_table_id=row.id).delete(
                synchronize_session=False
            )
            _suggest_column_mappings(db, row)

    plan.status = "draft"
    db.commit()
    return list_plan_tables(db, plan)


def suggest_mappings(db: Session, plan: MigrationPlan):
    tables = db.query(MigrationPlanTable).filter_by(plan_id=plan.id).all()
    for table in tables:
        db.query(MigrationColumnMapping).filter_by(plan_table_id=table.id).delete(
            synchronize_session=False
        )
        _suggest_column_mappings(db, table)
    plan.status = "draft"
    db.commit()
    return list_plan_tables(db, plan)


def update_column_mappings(
    db: Session,
    plan: MigrationPlan,
    table_id: uuid.UUID,
    payload: ColumnMappingsUpdate,
):
    table = db.query(MigrationPlanTable).filter_by(id=table_id, plan_id=plan.id).first()
    if table is None:
        raise HTTPException(status_code=404, detail="Migration table not found.")

    requested = {item.source_column: item for item in payload.mappings}
    if len(requested) != len(payload.mappings):
        raise HTTPException(status_code=422, detail="Each source column can be mapped only once.")
    source_columns = _columns_by_name(table.source_columns or [])
    if set(requested) - set(source_columns):
        raise HTTPException(
            status_code=422,
            detail="Mapping contains a source column that is not in the discovered source table.",
        )
    for item in payload.mappings:
        if item.included and not item.destination_column:
            raise HTTPException(
                status_code=422,
                detail=f"Included source column '{item.source_column}' needs a destination column name.",
            )

    destination_names = [
        item.destination_column
        for item in payload.mappings
        if item.included and item.destination_column
    ]
    if len(destination_names) != len(set(destination_names)):
        raise HTTPException(
            status_code=422,
            detail="Multiple source columns cannot map to the same destination column.",
        )

    destination_columns = _columns_by_name(table.destination_columns or [])
    if table.destination_exists:
        for item in payload.mappings:
            if item.included and item.destination_column not in destination_columns:
                raise HTTPException(
                    status_code=422,
                    detail=f"Destination column '{item.destination_column}' does not exist.",
                )

    db.query(MigrationColumnMapping).filter_by(plan_table_id=table.id).delete(
        synchronize_session=False
    )
    for item in payload.mappings:
        source_type = str(source_columns[item.source_column].get("type") or "TEXT")
        target_type = item.destination_type
        if table.destination_exists and item.destination_column:
            target = destination_columns.get(item.destination_column)
            if target_type is None and target:
                target_type = str(target.get("type") or source_type)
        else:
            target_type = target_type or source_type

        normalized_type = normalize_pg_type(target_type) if target_type else None
        if item.included and not table.destination_exists and not normalized_type:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported destination type '{target_type}' for column '{item.source_column}'.",
            )

        db.add(
            MigrationColumnMapping(
                plan_table_id=table.id,
                source_column=item.source_column,
                destination_column=item.destination_column,
                source_type=source_type,
                destination_type=target_type,
                included=item.included,
                compatible=types_compatible(source_type, target_type),
                match_strategy="manual",
            )
        )
    plan.status = "draft"
    db.commit()
    return (
        db.query(MigrationColumnMapping)
        .filter_by(plan_table_id=table.id)
        .order_by(MigrationColumnMapping.source_column)
        .all()
    )


def validate_plan(db: Session, plan: MigrationPlan):
    selected = db.query(MigrationPlanTable).filter_by(plan_id=plan.id, selected=True).all()
    errors: list[str] = []
    warnings: list[str] = []
    mapped_count = 0
    if not selected:
        errors.append("Select at least one source table.")

    destination_schema_names = {
        name
        for (name,) in db.query(DiscoveredSchema.name)
        .filter_by(snapshot_id=plan.destination_snapshot_id)
        .all()
    }
    targets: set[tuple[str, str]] = set()
    for table in selected:
        if (
            not plan.create_schemas
            and not table.destination_exists
            and table.destination_schema not in destination_schema_names
        ):
            errors.append(
                f"Destination schema '{table.destination_schema}' does not exist. Enable schema creation or choose an existing schema."
            )
        target_key = (table.destination_schema, table.destination_table)
        if target_key in targets:
            errors.append(
                f"More than one source table targets {table.destination_schema}.{table.destination_table}."
            )
        targets.add(target_key)

        mappings = db.query(MigrationColumnMapping).filter_by(plan_table_id=table.id).all()
        invalid_included = [
            item for item in mappings if item.included and not item.destination_column
        ]
        if invalid_included:
            errors.append(
                f"{table.source_schema}.{table.source_table} has included columns without destination names."
            )
        included = [item for item in mappings if item.included and item.destination_column]
        mapped_count += len(included)
        if not included:
            errors.append(f"{table.source_schema}.{table.source_table} has no included column mappings.")
            continue
        names = [item.destination_column for item in included]
        if len(names) != len(set(names)):
            errors.append(
                f"{table.source_schema}.{table.source_table} maps multiple columns to the same destination column."
            )
        if table.destination_exists:
            target_columns = _columns_by_name(table.destination_columns or [])
            for item in included:
                if item.destination_column not in target_columns:
                    errors.append(
                        f"Destination column {table.destination_schema}.{table.destination_table}.{item.destination_column} does not exist."
                    )
                elif not item.compatible:
                    warnings.append(
                        f"Type conversion may be required for {table.source_schema}.{table.source_table}.{item.source_column}."
                    )
        else:
            for item in included:
                if not normalize_pg_type(item.destination_type or item.source_type):
                    errors.append(
                        f"Unsupported destination type for {table.source_schema}.{table.source_table}.{item.source_column}."
                    )
        if table.source_table_type != "table":
            errors.append(f"{table.source_schema}.{table.source_table} is not a regular table.")
        if table.estimated_rows is not None:
            warnings.append(
                f"{table.source_schema}.{table.source_table} has an estimated {table.estimated_rows} rows; the estimate is not an exact count."
            )

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": sorted(set(warnings)),
        "selected_table_count": len(selected),
        "mapped_column_count": mapped_count,
    }


def validate_and_update_plan(db: Session, plan: MigrationPlan):
    result = validate_plan(db, plan)
    plan.status = "ready" if result["valid"] else "draft"
    db.commit()
    return result


def preview_ddl(db: Session, plan: MigrationPlan):
    tables = db.query(MigrationPlanTable).filter_by(plan_id=plan.id, selected=True).all()
    mappings = {
        table.id: db.query(MigrationColumnMapping).filter_by(plan_table_id=table.id).all()
        for table in tables
    }
    statements, warnings, table_count, schemas = build_ddl(
        tables, mappings, plan.create_schemas
    )
    return {
        "statements": statements,
        "warnings": warnings,
        "tables_to_create": table_count,
        "schemas_to_create": schemas,
    }


def apply_ddl(db: Session, user: User, project_id: uuid.UUID, plan: MigrationPlan):
    validation = validate_plan(db, plan)
    if not validation["valid"]:
        raise HTTPException(
            status_code=409,
            detail={"message": "Migration plan is not valid.", **validation},
        )
    preview = preview_ddl(db, plan)
    from app.services.discovery_service import _engine_for

    connection = connection_service.get_connection(
        db, user, project_id, plan.destination_connection_id
    )
    engine = _engine_for(connection)
    try:
        with engine.begin() as remote:
            for statement in preview["statements"]:
                remote.exec_driver_sql(statement)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Destination schema preparation failed ({type(exc).__name__}). No migration rows were transferred.",
        ) from exc
    finally:
        engine.dispose()

    tables = db.query(MigrationPlanTable).filter_by(plan_id=plan.id, selected=True).all()
    for table in tables:
        if table.destination_exists or table.source_table_type != "table":
            continue
        mappings = db.query(MigrationColumnMapping).filter_by(plan_table_id=table.id).all()
        table.destination_columns = [
            {
                "name": item.destination_column,
                "type": item.destination_type or item.source_type,
                "nullable": next(
                    (
                        column.get("nullable", True)
                        for column in table.source_columns
                        if column.get("name") == item.source_column
                    ),
                    True,
                ),
            }
            for item in mappings
            if item.included and item.destination_column
        ]
        table.destination_exists = True

    plan.status = "schema_prepared"
    db.commit()
    return {
        "success": True,
        "message": "Destination schema statements were applied successfully. No row data was transferred.",
        **preview,
    }
