import os
import unittest
from unittest.mock import patch

from snowbridge.config import Settings


class SettingsTests(unittest.TestCase):
    def test_reads_snowbridge_prefixed_environment(self):
        with patch.dict(os.environ, {
            "SNOWBRIDGE_ENV": "test",
            "SNOWBRIDGE_LOG_LEVEL": "DEBUG",
            "SNOWBRIDGE_CONNECT_TIMEOUT_SECONDS": "4",
        }, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.environment, "test")
        self.assertEqual(settings.log_level, "DEBUG")
        self.assertEqual(settings.connect_timeout_seconds, 4)

    def test_rejects_invalid_timeouts(self):
        with patch.dict(os.environ, {"SNOWBRIDGE_CONNECT_TIMEOUT_SECONDS": "0"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()


if __name__ == "__main__":
    unittest.main()
