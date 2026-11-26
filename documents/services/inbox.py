"""Watched-folder intake: pick up dropped files and run the normal pipeline."""

from __future__ import annotations

import logging
import mimetypes
import shutil
import time
from pathlib import Path

from django.conf import settings

from documents.services.intake import process_upload
from documents.services.validation import ALLOWED_EXTENSIONS

logger = logging.getLogger(__name__)


def _content_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def scan_inbox_once(inbox_dir: Path | str | None = None) -> list[str]:
    """Process every eligible file in the inbox; returns processed filenames."""
    root = Path(inbox_dir or settings.APP["inbox_dir"])
    processed_dir = root / "processed"
    failed_dir = root / "failed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)

    handled: list[str] = []
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        # Extensionless files are still tried: validation sniffs the bytes
        # and assigns the right extension.
        if suffix and suffix not in ALLOWED_EXTENSIONS:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            logger.exception("Could not read inbox file %s", path)
            continue
        result = process_upload(data, path.name, _content_type(path))
        target_dir = failed_dir if result.error else processed_dir
        destination = target_dir / path.name
        counter = 1
        while destination.exists():
            destination = target_dir / f"{path.stem}-{counter}{path.suffix}"
            counter += 1
        shutil.move(str(path), destination)
        handled.append(path.name)
        if result.error:
            logger.warning("Inbox file %s failed: %s", path.name, result.error)
        elif result.duplicate:
            logger.info("Inbox file %s was a duplicate", path.name)
    return handled


def watch_inbox(poll_seconds: float | None = None) -> None:  # pragma: no cover
    """Blocking loop used by the `watch_inbox` management command."""
    interval = float(
        poll_seconds if poll_seconds is not None else settings.APP["inbox_poll_seconds"]
    )
    sync_interval = float(settings.APP.get("paperless_sync_seconds") or 0)
    recovery_interval = float(settings.APP.get("recovery_interval_seconds") or 0)
    last_sync = 0.0
    last_recovery = 0.0
    webhook_ok = False
    try:
        from documents.management.commands.provision_paperless_webhook import (
            provision_paperless_webhook,
        )

        webhook_ok, detail = provision_paperless_webhook()
        logger.info(
            "Paperless webhook provision: %s (%s)", "ok" if webhook_ok else "failed", detail
        )
    except Exception:
        logger.exception("Paperless webhook provisioning failed")
    logger.info("Watching inbox every %.1fs", interval)
    while True:
        try:
            scan_inbox_once()
        except Exception:
            logger.exception("Inbox scan failed")
        now = time.monotonic()
        if sync_interval > 0 and now - last_sync >= sync_interval:
            last_sync = now
            try:
                from documents.management.commands.provision_paperless_webhook import (
                    provision_paperless_webhook,
                )
                from documents.services.sync import sync_paperless_documents

                if not webhook_ok:
                    webhook_ok, detail = provision_paperless_webhook()
                    if webhook_ok:
                        logger.info("Paperless webhook provisioned on retry: %s", detail)
                result = sync_paperless_documents()
                if result.ingested or result.errors:
                    logger.info(
                        "Paperless sync: %d scanned, %d ingested, %d errors",
                        result.scanned,
                        result.ingested,
                        len(result.errors),
                    )
            except Exception:
                logger.exception("Paperless sync failed")
        now = time.monotonic()
        if recovery_interval > 0 and now - last_recovery >= recovery_interval:
            last_recovery = now
            try:
                from documents.services.recovery import recover_stuck

                recover_stuck()
            except Exception:
                logger.exception("Stuck-work recovery failed")
        time.sleep(interval)
