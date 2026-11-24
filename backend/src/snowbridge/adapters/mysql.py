"""MySQL 8+ catalog discovery adapter (mysql-connector-python optional)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Sequence
from snowbridge.contracts import Capability, CapabilityStatus, Column, Key, TableSchema
try:
    import mysql.connector as mysql_connector
except ImportError:
    mysql_connector = None

@dataclass(frozen=True, slots=True)
class MySQLEndpoint:
    host: str
    database: str
    username: str
    password: str
    port: int = 3306
    connect_timeout: int = 10
    ssl_ca: str | None = None

class MySQLAdapter:
    def __init__(self, endpoint: MySQLEndpoint):
        self.endpoint = endpoint

    def connect(self):
        if mysql_connector is None:
            raise RuntimeError("Install Snowbridge with the [mysql] extra to use MySQL discovery")
        options: dict[str, Any] = dict(host=self.endpoint.host, port=self.endpoint.port,
            database=self.endpoint.database, user=self.endpoint.username,
            password=self.endpoint.password, connection_timeout=self.endpoint.connect_timeout,
            autocommit=True)
        if self.endpoint.ssl_ca:
            options.update(ssl_ca=self.endpoint.ssl_ca, ssl_verify_cert=True)
        return mysql_connector.connect(**options)

    def inspect_capabilities(self) -> Sequence[Capability]:
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT VERSION(), @@version_comment, @@binlog_format, @@log_bin, @@gtid_mode")
            version, comment, binlog_format, log_bin, gtid_mode = cur.fetchone()
            cur.execute("SHOW GRANTS")
            grants = " ".join(str(r[0]).upper() for r in cur.fetchall())
            repl_ok = "REPLICATION" in grants or "ALL PRIVILEGES" in grants
            if not log_bin:
                bin_status, bin_reason = CapabilityStatus.REQUIRES_CONFIGURATION, "Enable binary logging (log_bin=ON)."
            elif str(binlog_format).upper() != "ROW":
                bin_status, bin_reason = CapabilityStatus.REQUIRES_CONFIGURATION, "Set binlog_format=ROW for row-based CDC."
            elif not repl_ok:
                bin_status, bin_reason = CapabilityStatus.REQUIRES_PERMISSION, "Grant replication client/replica privileges for CDC."
            else:
                bin_status, bin_reason = CapabilityStatus.AVAILABLE, "ROW binary logging and replication grants are present."
            return (
                Capability("innodb_consistent_snapshot", CapabilityStatus.AVAILABLE,
                           "InnoDB supports REPEATABLE READ consistent snapshots; non-InnoDB tables need separate handling."),
                Capability("row_based_binlog", bin_status, bin_reason,
                           requirements=("log_bin=ON", "binlog_format=ROW"),
                           permission_checks=("REPLICATION CLIENT", "REPLICATION SLAVE or REPLICATION REPLICA")),
                Capability("gtid", CapabilityStatus.AVAILABLE if str(gtid_mode).upper() not in {"OFF", ""} else CapabilityStatus.REQUIRES_CONFIGURATION,
                           f"gtid_mode={gtid_mode}; GTID is recommended for failover-safe CDC."),
                Capability("load_data", CapabilityStatus.AVAILABLE, "LOAD DATA is supported subject to secure_file_priv and client policy."),
            )
        finally:
            conn.close()

    def discover_schema(self, schemas: Sequence[str] | None = None) -> list[TableSchema]:
        conn = self.connect()
        try:
            cur = conn.cursor()
            selected = tuple(schemas) if schemas else (self.endpoint.database,)
            marks = ",".join(["%s"] * len(selected))
            cur.execute(f"""SELECT TABLE_SCHEMA,TABLE_NAME,TABLE_ROWS,DATA_LENGTH+INDEX_LENGTH,
                    ENGINE,TABLE_COMMENT FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA IN ({marks}) AND TABLE_TYPE='BASE TABLE'
                    ORDER BY TABLE_SCHEMA,TABLE_NAME""", selected)
            result=[]
            for schema, table, rows, size, engine, comment in cur.fetchall():
                cur.execute("""SELECT COLUMN_NAME,ORDINAL_POSITION,COLUMN_TYPE,IS_NULLABLE,
                    NUMERIC_PRECISION,NUMERIC_SCALE,CHARACTER_MAXIMUM_LENGTH,COLUMN_DEFAULT,
                    EXTRA,COLLATION_NAME FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION""",(schema,table))
                columns=tuple(Column(name=r[0],ordinal=int(r[1]),native_type=str(r[2]),
                    nullable=str(r[3]).upper()=="YES",precision=int(r[4]) if r[4] is not None else None,
                    scale=int(r[5]) if r[5] is not None else None,length=int(r[6]) if r[6] is not None else None,
                    default_expression=str(r[7]) if r[7] is not None else None,
                    generated_kind=("stored" if "STORED GENERATED" in str(r[8]).upper() else
                                    "virtual" if "VIRTUAL GENERATED" in str(r[8]).upper() else None),
                    identity_kind="auto_increment" if "auto_increment" in str(r[8]).lower() else None,
                    collation=r[9]) for r in cur.fetchall())
                cur.execute("""SELECT INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME
                    FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
                    ORDER BY INDEX_NAME,SEQ_IN_INDEX""",(schema,table))
                groups={}; unique={}
                for name, non_unique, seq, col in cur.fetchall():
                    if col is not None:
                        groups.setdefault(str(name),[]).append((int(seq),str(col)))
                        unique[str(name)]=not bool(non_unique)
                keys=tuple(Key(n,tuple(c for _,c in sorted(cols)),n=="PRIMARY",unique[n])
                    for n,cols in groups.items() if unique[n])
                result.append(TableSchema(str(schema),str(table),columns,keys,
                    max(0,int(rows)) if rows is not None else None,False,
                    estimated_bytes=max(0,int(size)) if size is not None else None,
                    storage_engine=str(engine) if engine else None,comment=str(comment or "")))
            return result
        finally:
            conn.close()
