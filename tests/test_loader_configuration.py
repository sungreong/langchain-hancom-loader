from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_hancom_loader import HancomDataLoader


class LoaderConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.document = Path(self.temporary_directory.name) / "sample.pdf"
        self.document.write_bytes(b"%PDF-1.4\n")

    def test_uses_explicit_webhook_url_before_environment_value(self) -> None:
        with patch.dict(
            os.environ,
            {
                "HANCOM_API_KEY": "test-key",
                "HANCOM_WEBHOOK_URL": "https://environment.example/hancom/webhook",
            },
            clear=True,
        ):
            loader = HancomDataLoader(
                self.document,
                webhook_url="https://explicit.example/hancom/webhook",
            )

        self.assertEqual(loader.webhook_url, "https://explicit.example/hancom/webhook")

    def test_uses_webhook_url_from_application_environment(self) -> None:
        expected_url = "https://environment.example/hancom/webhook"
        with patch.dict(
            os.environ,
            {"HANCOM_API_KEY": "test-key", "HANCOM_WEBHOOK_URL": expected_url},
            clear=True,
        ):
            loader = HancomDataLoader(self.document)

        self.assertEqual(loader.webhook_url, expected_url)

    def test_requires_a_webhook_url_from_the_caller(self) -> None:
        runtime_directory = self.document.parent / ".runtime"
        runtime_directory.mkdir()
        (runtime_directory / "hancom-webhook.env").write_text(
            "HANCOM_WEBHOOK_URL=https://ignored.example/hancom/webhook\n",
            encoding="utf-8",
        )
        previous_directory = Path.cwd()
        with patch.dict(os.environ, {"HANCOM_API_KEY": "test-key"}, clear=True):
            os.chdir(self.document.parent)
            try:
                with self.assertRaisesRegex(ValueError, "HANCOM_WEBHOOK_URL"):
                    HancomDataLoader(self.document)
            finally:
                os.chdir(previous_directory)


if __name__ == "__main__":
    unittest.main()
