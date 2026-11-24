"""Optional live catalog checks; set vendor environment variables to enable."""
import os
import unittest
from snowbridge.adapters.postgresql import PostgresAdapter,PostgresEndpoint
from snowbridge.adapters.mysql import MySQLAdapter,MySQLEndpoint
from snowbridge.adapters.oracle import OracleAdapter,OracleEndpoint
from snowbridge.discovery import discover_inventory

class CrossEngineCatalogIntegration(unittest.TestCase):
    def _check(self,name,adapter):
        report=discover_inventory(adapter,name)
        self.assertEqual(report.engine,name)
        for table in report.tables:
            self.assertTrue(table.columns, f"{table.schema_name}.{table.table_name} has no columns")
            self.assertEqual([c.ordinal for c in table.columns],sorted(c.ordinal for c in table.columns))
    def test_postgresql_catalog_when_configured(self):
        dsn=os.getenv("SNOWBRIDGE_TEST_POSTGRES_DSN")
        if not dsn:self.skipTest("SNOWBRIDGE_TEST_POSTGRES_DSN not configured")
        self._check("postgresql",PostgresAdapter(PostgresEndpoint(dsn)))
    def test_mysql_catalog_when_configured(self):
        required=("SNOWBRIDGE_TEST_MYSQL_HOST","SNOWBRIDGE_TEST_MYSQL_DATABASE",
                  "SNOWBRIDGE_TEST_MYSQL_USER","SNOWBRIDGE_TEST_MYSQL_PASSWORD")
        if not all(os.getenv(k) for k in required):self.skipTest("MySQL test connection variables not configured")
        self._check("mysql",MySQLAdapter(MySQLEndpoint(os.environ[required[0]],os.environ[required[1]],
            os.environ[required[2]],os.environ[required[3]],port=int(os.getenv("SNOWBRIDGE_TEST_MYSQL_PORT","3306")))))
    def test_oracle_catalog_when_configured(self):
        required=("SNOWBRIDGE_TEST_ORACLE_USER","SNOWBRIDGE_TEST_ORACLE_PASSWORD","SNOWBRIDGE_TEST_ORACLE_DSN")
        if not all(os.getenv(k) for k in required):self.skipTest("Oracle test connection variables not configured")
        self._check("oracle",OracleAdapter(OracleEndpoint(os.environ[required[0]],os.environ[required[1]],os.environ[required[2]])))

if __name__=="__main__":unittest.main()
