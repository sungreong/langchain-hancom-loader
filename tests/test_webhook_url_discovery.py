from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_hancom_loader import HancomDataLoader


class WebhookUrlDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.document = self.root / "sample.pdf"
        self.document.write_bytes(b"%PDF-1.4\n")

    def test_reads_generated_runtime_webhook_url(self) -> None:
        runtime_directory = self.root / ".runtime"
        runtime_directory.mkdir()
        expected_url = "https://generated.trycloudflare.com/hancom/webhook"
        (runtime_directory / "hancom-webhook.env").write_text(
            f"HANCOM_WEBHOOK_URL={expected_url}\n",
            encoding="utf-8",
        )

        previous_directory = Path.cwd()
        with patch.dict(os.environ, {"HANCOM_API_KEY": "test-key"}, clear=False):
            os.environ.pop("HANCOM_WEBHOOK_URL", None)
            os.environ.pop("HANCOM_WEBHOOK_ENV_FILE", None)
            os.chdir(self.root)
            try:
                loader = HancomDataLoader(self.document)
            finally:
                os.chdir(previous_directory)

        self.assertEqual(loader.webhook_url, expected_url)

    def test_explicit_url_wins_over_environment_and_runtime_file(self) -> None:
        runtime_file = self.root / "webhook.env"
        runtime_file.write_text(
            "HANCOM_WEBHOOK_URL=https://file.example/hancom/webhook\n",
            encoding="utf-8",
        )
        explicit_url = "https://explicit.example/hancom/webhook"

        with patch.dict(
            os.environ,
            {
                "HANCOM_API_KEY": "test-key",
                "HANCOM_WEBHOOK_URL": "https://environment.example/hancom/webhook",
                "HANCOM_WEBHOOK_ENV_FILE": str(runtime_file),
            },
            clear=False,
        ):
            loader = HancomDataLoader(self.document, webhook_url=explicit_url)

        self.assertEqual(loader.webhook_url, explicit_url)

    def test_environment_url_wins_over_runtime_file(self) -> None:
        runtime_file = self.root / "webhook.env"
        runtime_file.write_text(
            "HANCOM_WEBHOOK_URL=https://file.example/hancom/webhook\n",
            encoding="utf-8",
        )
        environment_url = "https://environment.example/hancom/webhook"

        with patch.dict(
            os.environ,
            {
                "HANCOM_API_KEY": "test-key",
                "HANCOM_WEBHOOK_URL": environment_url,
                "HANCOM_WEBHOOK_ENV_FILE": str(runtime_file),
            },
            clear=False,
        ):
            loader = HancomDataLoader(self.document)

        self.assertEqual(loader.webhook_url, environment_url)


if __name__ == "__main__":
    unittest.main()
