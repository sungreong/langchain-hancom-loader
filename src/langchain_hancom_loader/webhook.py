"""Small HTTP receiver for Hancom Data Loader completion callbacks.

The receiver acknowledges callback requests at ``/hancom/webhook``. It discards
valid payloads by default so that installing the package does not create a
document-data store. Use ``--output-dir`` only while diagnosing integrations.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

MAX_BODY_BYTES = 64 * 1024


def create_handler(output_dir: Path | None = None) -> type[BaseHTTPRequestHandler]:
    """Create a callback handler, optionally persisting valid JSON payloads."""

    class WebhookHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/healthz":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/hancom/webhook":
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            content_length = self.headers.get("Content-Length")
            try:
                size = int(content_length) if content_length is not None else -1
            except ValueError:
                size = -1
            if size < 0 or size > MAX_BODY_BYTES:
                self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return

            try:
                payload = json.loads(self.rfile.read(size))
            except json.JSONDecodeError:
                self.send_error(HTTPStatus.BAD_REQUEST, "Webhook body must be JSON.")
                return
            if not isinstance(payload, Mapping):
                self.send_error(HTTPStatus.BAD_REQUEST, "Webhook payload must be a JSON object.")
                return

            if output_dir is not None:
                event = {
                    "received_at": datetime.now(timezone.utc).isoformat(),
                    "payload": payload,
                }
                write_event(output_dir, event)

            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return None

    return WebhookHandler


def write_event(output_dir: Path, event: Mapping[str, object]) -> Path:
    """Atomically save an event and update the latest-event pointer."""
    output_dir.mkdir(parents=True, exist_ok=True)
    contents = json.dumps(event, ensure_ascii=False, indent=2, default=str) + "\n"
    event_path = output_dir / f"{time.time_ns()}.json"
    _atomic_write(event_path, contents)
    _atomic_write(output_dir / "latest.json", contents)
    return event_path


def _atomic_write(path: Path, contents: str) -> None:
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(contents, encoding="utf-8")
    temporary_path.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Receive Hancom Data Loader completion callbacks."
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional directory for callback payloads. Payloads are discarded by default.",
    )
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), create_handler(args.output_dir))
    print(f"Listening for Hancom webhooks on http://{args.host}:{args.port}/hancom/webhook")
    server.serve_forever()


if __name__ == "__main__":
    main()
