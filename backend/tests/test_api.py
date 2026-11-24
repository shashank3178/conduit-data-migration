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
        self.assertFalse(value.tls)

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
