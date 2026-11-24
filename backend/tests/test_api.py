"""Smoke tests for the local API surface."""
import unittest

from snowbridge.api import app
from snowbridge.api import ConnectionInput, DiscoveryRequest


class ApiSurfaceTests(unittest.TestCase):
    def test_health_and_discovery_routes_are_registered(self):
        paths = {route.path for route in app.routes}
        self.assertIn("/api/health", paths)
        self.assertIn("/api/connections/test", paths)
        self.assertIn("/api/connections", paths)
        self.assertIn("/api/connections/{connection_id}", paths)
        self.assertIn("/api/discovery", paths)
        self.assertIn("/api/migrations", paths)

    def test_connection_input_defaults_to_postgresql(self):
        value = ConnectionInput(
            host="localhost", database="sample", username="reader", password="secret"
        )
        self.assertEqual(value.engine, "postgresql")
        self.assertTrue(value.tls)
        self.assertEqual(value.sslmode, "require")
        self.assertEqual(value.connect_timeout, 10)

    def test_postgres_connection_options_are_validated_and_encoded(self):
        from snowbridge.api import _dsn
        value = ConnectionInput(
            host="ep-example-pooler.ap-southeast-1.aws.neon.tech",
            database="app db", username="owner@example", password="p@ss/word",
            sslmode="verify-full", connect_timeout=25, hostaddr="203.0.113.10",
            application_name="snowbridge test",
        )
        dsn = _dsn(value)
        self.assertIn("sslmode=verify-full", dsn)
        self.assertIn("connect_timeout=25", dsn)
        self.assertIn("hostaddr=203.0.113.10", dsn)
        self.assertIn("application_name=snowbridge+test", dsn)
        self.assertIn("p%40ss%2Fword", dsn)

    def test_api_discovery_accepts_schema_scope(self):
        request = DiscoveryRequest(
            connection=ConnectionInput(
                engine="mysql", host="localhost", port=3306,
                database="sample", username="reader", password="secret"
            ),
            schemas=["sales"],
        )
        self.assertEqual(request.schemas, ["sales"])
        self.assertEqual(request.connection.engine, "mysql")


if __name__ == "__main__":
    unittest.main()
