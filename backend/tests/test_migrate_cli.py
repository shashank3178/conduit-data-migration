import unittest
from unittest.mock import patch

from snowbridge.config import Settings
from snowbridge.metadata.migrate import resolve_dsn


class ResolveDsnTests(unittest.TestCase):
    def test_explicit_dsn_takes_precedence(self):
        with patch.object(Settings, "from_env", side_effect=AssertionError("must not load settings")):
            self.assertEqual(
                resolve_dsn("  postgresql://explicit/db  "),
                "postgresql://explicit/db",
            )

    def test_falls_back_to_settings(self):
        configured = Settings(metadata_database_url="postgresql://dotenv/db")
        with patch.object(Settings, "from_env", return_value=configured):
            self.assertEqual(resolve_dsn(None), "postgresql://dotenv/db")

    def test_missing_dsn_has_actionable_error(self):
        with patch.object(Settings, "from_env", return_value=Settings()):
            with self.assertRaisesRegex(ValueError, "backend/.env"):
                resolve_dsn(None)


if __name__ == "__main__":
    unittest.main()
