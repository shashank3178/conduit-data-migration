"""Oracle 19c+ catalog discovery adapter (python-oracledb optional)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Sequence
from snowbridge.contracts import Capability, CapabilityStatus, Column, Key, TableSchema
try:
    import oracledb
except ImportError:
    oracledb = None

@dataclass(frozen=True, slots=True)
class OracleEndpoint:
    user: str
    password: str
    dsn: str
    connect_timeout: int = 10

class OracleAdapter:
    def __init__(self, endpoint: OracleEndpoint):
        self.endpoint=endpoint

    def connect(self):
        if oracledb is None:
            raise RuntimeError("Install Snowbridge with the [oracle] extra to use Oracle discovery")
        return oracledb.connect(user=self.endpoint.user,password=self.endpoint.password,
            dsn=self.endpoint.dsn,tcp_connect_timeout=self.endpoint.connect_timeout)

    @staticmethod
    def _query(conn: Any, statement: str, binds: dict[str,Any] | None=None):
        cur=conn.cursor()
        try:
            cur.execute(statement,binds or {})
            return cur.fetchall()
        finally:
            cur.close()

    def inspect_capabilities(self) -> Sequence[Capability]:
        conn=self.connect()
        try:
            version=self._query(conn,"SELECT version FROM product_component_version WHERE product LIKE 'Oracle Database%'")
            version_text=str(version[0][0]) if version else "unknown"
            privs={str(r[0]).upper() for r in self._query(conn,"SELECT privilege FROM session_privs")}
            logminer=("LOGMINING" in privs or "SELECT ANY TRANSACTION" in privs)
            return (
                Capability("consistent_scn_read",CapabilityStatus.AVAILABLE,
                    "Flashback query at a consistent SCN is available subject to UNDO retention."),
                Capability("logminer",CapabilityStatus.AVAILABLE if logminer else CapabilityStatus.REQUIRES_PERMISSION,
                    "LogMiner privileges are present." if logminer else
                    "Grant approved LogMiner/transaction-query privileges and configure ARCHIVELOG and supplemental logging.",
                    requirements=("ARCHIVELOG","supplemental logging","adequate UNDO/archive retention"),
                    permission_checks=("LOGMINING or SELECT ANY TRANSACTION",)),
                Capability("direct_path_load",CapabilityStatus.AVAILABLE,
                    "Direct-path/array loading is available subject to table and constraint restrictions."),
            )
        finally:
            conn.close()

    def discover_schema(self, schemas: Sequence[str] | None = None) -> list[TableSchema]:
        conn=self.connect()
        try:
            owners=[s.upper() for s in schemas] if schemas else [
                str(self._query(conn,"SELECT SYS_CONTEXT('USERENV','CURRENT_SCHEMA') FROM dual")[0][0])]
            result=[]
            for owner in owners:
                tables=self._query(conn,"""SELECT t.table_name,t.num_rows,t.avg_row_len,
                    t.partitioned,tc.comments FROM all_tables t LEFT JOIN all_tab_comments tc
                    ON tc.owner=t.owner AND tc.table_name=t.table_name
                    WHERE t.owner=:owner ORDER BY t.table_name""",{"owner":owner})
                for table,num_rows,avg_len,partitioned,comment in tables:
                    cols=self._query(conn,"""SELECT column_name,column_id,data_type,nullable,
                        data_precision,data_scale,char_length,data_length,data_default,
                        virtual_column,identity_column,collation FROM all_tab_cols
                        WHERE owner=:owner AND table_name=:table AND hidden_column='NO'
                        ORDER BY column_id""",{"owner":owner,"table":table})
                    columns=tuple(Column(name=str(r[0]),ordinal=int(r[1]),native_type=str(r[2]),
                        nullable=str(r[3])=="Y",precision=int(r[4]) if r[4] is not None else None,
                        scale=int(r[5]) if r[5] is not None else None,
                        length=int(r[6]) if r[6] is not None else (int(r[7]) if r[7] is not None else None),
                        default_expression=str(r[8]).strip() if r[8] is not None else None,
                        generated_kind="virtual" if str(r[9])=="YES" else None,
                        identity_kind="identity" if str(r[10])=="YES" else None,
                        collation=str(r[11]) if r[11] else None) for r in cols)
                    keyrows=self._query(conn,"""SELECT c.constraint_name,c.constraint_type,
                        cc.position,cc.column_name FROM all_constraints c JOIN all_cons_columns cc
                        ON cc.owner=c.owner AND cc.constraint_name=c.constraint_name
                        AND cc.table_name=c.table_name WHERE c.owner=:owner AND c.table_name=:table
                        AND c.constraint_type IN ('P','U') AND c.status='ENABLED'
                        ORDER BY c.constraint_name,cc.position""",{"owner":owner,"table":table})
                    groups={}; kinds={}
                    for name,kind,pos,col in keyrows:
                        groups.setdefault(str(name),[]).append((int(pos),str(col))); kinds[str(name)]=str(kind)
                    keys=tuple(Key(n,tuple(c for _,c in sorted(cols)),kinds[n]=="P",True)
                        for n,cols in groups.items())
                    size=int(avg_len)*int(num_rows) if avg_len is not None and num_rows is not None else None
                    result.append(TableSchema(owner,str(table),columns,keys,
                        max(0,int(num_rows)) if num_rows is not None else None,
                        str(partitioned)=="YES",estimated_bytes=size,storage_engine="oracle",
                        comment=str(comment or "")))
            return result
        finally:
            conn.close()
