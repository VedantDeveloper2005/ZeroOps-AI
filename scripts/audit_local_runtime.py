"""Start the real API against a disposable local PostgreSQL audit database.

Only this explicit test entry point replaces Key Vault configuration and email
delivery. It never reads production secrets. No worker or cloud adapter is
started. Mail is captured under the supplied temporary directory for the HTTP
smoke test; this is not evidence of external SMTP/SMS delivery.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory.resolve(strict=True)
    repository = Path(__file__).resolve().parents[1]
    if not directory.is_relative_to(repository / "tmp"):
        parser.error("Audit files must stay in a dedicated directory under tmp/.")
    sys.path.insert(0, str(repository))
    os.environ["APP_ENV"] = "test"
    os.environ["AZURE_KEYVAULT_URL"] = ""

    from backend.services import vault

    settings = {
        "DATABASE_URL": "postgresql+asyncpg://audit_runner@127.0.0.1:55439/zeroops_audit",
        "DB_SSL_ENABLED": "false",
        "JWT_SECRET": secrets.token_urlsafe(48),
        "WORKER_EVENT_TOKEN": secrets.token_urlsafe(48),
        "FRONTEND_URL": "http://localhost:3000",
        "ZEROOPS_BACKEND_URL": "http://127.0.0.1:18000",
        "PHONE_VERIFICATION_REQUIRED": "false",
    }
    vault.get_application_setting = lambda name, *, default="", required=False: settings.get(name, default)

    from backend import config
    from backend.services import email_service

    config.WORKSPACE_DIR = str(directory / "workspace")
    Path(config.WORKSPACE_DIR).mkdir(exist_ok=True)
    messages: list[dict[str, str]] = []

    def capture_email(to_email: str, subject: str, html: str, text: str) -> bool:
        messages.append({"to": to_email, "subject": subject, "text": text})
        (directory / "mailbox.json").write_text(json.dumps(messages), encoding="utf-8")
        return True

    email_service.is_configured = lambda: True
    email_service._send_email = capture_email

    from backend.main import app
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=18000, access_log=False)


if __name__ == "__main__":
    main()
