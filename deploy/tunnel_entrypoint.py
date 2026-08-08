"""Run a Cloudflare Quick Tunnel and publish its generated webhook URL."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
from pathlib import Path

_QUICK_TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def _atomic_write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(contents, encoding="utf-8")
    temporary_path.replace(path)


def main() -> None:
    target_url = os.environ.get("TUNNEL_TARGET_URL", "http://host.docker.internal:8000")
    webhook_path = os.environ.get("HANCOM_WEBHOOK_PATH", "/hancom/webhook")
    environment_file = Path(
        os.environ.get("HANCOM_WEBHOOK_ENV_FILE", "/runtime/hancom-webhook.env")
    )
    environment_file.unlink(missing_ok=True)

    process = subprocess.Popen(
        [
            "cloudflared",
            "tunnel",
            "--no-autoupdate",
            "--url",
            target_url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    def forward_signal(signum: int, _frame: object) -> None:
        if process.poll() is None:
            process.send_signal(signum)

    signal.signal(signal.SIGTERM, forward_signal)
    signal.signal(signal.SIGINT, forward_signal)

    try:
        webhook_url: str | None = None
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            if webhook_url is not None:
                continue
            match = _QUICK_TUNNEL_URL.search(line)
            if match is None:
                continue
            webhook_url = f"{match.group(0)}{webhook_path}"
            _atomic_write(
                environment_file,
                f"HANCOM_WEBHOOK_URL={webhook_url}\n",
            )
            print(f"HANCOM_WEBHOOK_URL={webhook_url}", flush=True)
            print(f"Saved webhook URL to {environment_file}", flush=True)

        return_code = process.wait()
    finally:
        environment_file.unlink(missing_ok=True)

    raise SystemExit(return_code)


if __name__ == "__main__":
    main()
