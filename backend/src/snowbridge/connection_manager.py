"""Connection lifecycle based on opaque secret references."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus
from snowbridge.contracts import SecretProvider,SecretReference
from snowbridge.type_mapping import normalize_engine

@dataclass(frozen=True,slots=True)
class ConnectionSpec:
    connection_id:str
    engine:str
    host:str
    database:str
    username:str
    secret_ref:SecretReference
    port:int|None=None
    connect_timeout_seconds:int=10
    tls_required:bool=True
    def __post_init__(self):
        object.__setattr__(self,"engine",normalize_engine(self.engine))
        if not all((self.connection_id,self.host,self.database,self.username)):raise ValueError("connection id, host, database and username are required")
        if self.connect_timeout_seconds<=0:raise ValueError("connect timeout must be positive")

class ConnectionManager:
    def __init__(self,secret_provider:SecretProvider):self.secret_provider=secret_provider
    def create_adapter(self,spec:ConnectionSpec):
        secret=self.secret_provider.resolve(spec.secret_ref); password=secret.get("password")
        if not password:raise ValueError("resolved secret must contain a non-empty password")
        if spec.engine=="postgresql":
            from snowbridge.adapters.postgresql import PostgresAdapter,PostgresEndpoint
            port=spec.port or 5432
            dsn=(f"postgresql://{quote_plus(spec.username)}:{quote_plus(password)}@{spec.host}:{port}/"
                 f"{quote_plus(spec.database)}?connect_timeout={spec.connect_timeout_seconds}"
                 f"&sslmode={'require' if spec.tls_required else 'prefer'}")
            return PostgresAdapter(PostgresEndpoint(dsn,spec.connect_timeout_seconds))
        if spec.engine=="mysql":
            from snowbridge.adapters.mysql import MySQLAdapter,MySQLEndpoint
            return MySQLAdapter(MySQLEndpoint(spec.host,spec.database,spec.username,password,
                port=spec.port or 3306,connect_timeout=spec.connect_timeout_seconds,
                ssl_ca=secret.get("ssl_ca") if spec.tls_required else None))
        from snowbridge.adapters.oracle import OracleAdapter,OracleEndpoint
        return OracleAdapter(OracleEndpoint(spec.username,password,spec.database,spec.connect_timeout_seconds))
    def test_connection(self,spec:ConnectionSpec)->dict[str,Any]:
        adapter=self.create_adapter(spec)
        return {"connection_id":spec.connection_id,"engine":spec.engine,
                "connected":True,"capabilities":tuple(adapter.inspect_capabilities())}
