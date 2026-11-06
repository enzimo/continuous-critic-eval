"""Durable delivery for CLI clients. Credentials never enter the outbox."""

import fcntl
import hashlib
import logging
import os
from pathlib import Path
from uuid import uuid4

import httpx

from .models import MAX_BATCH_BYTES, Batch

log = logging.getLogger(__name__)


class DeliveryError(RuntimeError):
    pass


def batch_body(batch: Batch) -> bytes:
    """Use the same compact UTF-8 bytes for size checks and HTTP delivery."""
    return batch.model_dump_json().encode("utf-8")


class Reporter:
    def __init__(self, server, token, queue_dir=None):
        self.server = server.rstrip("/")
        if not self.server.startswith(("http://", "https://")):
            raise ValueError("Server must be an http(s) URL")
        self.token = token
        base = Path(queue_dir) if queue_dir else Path.home() / ".local/state/critic-observer/outbox"
        self.directory = base / hashlib.sha256(self.server.encode()).hexdigest()[:16]
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)

    def request(self, method, path, **kwargs):
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            response = client.request(
                method,
                self.server + path,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                **kwargs,
            )
        if response.is_error or response.is_redirect:
            # Validation details can quote submitted evidence. Keep diagnostics out of shared logs.
            raise DeliveryError(
                f"Collector returned HTTP {response.status_code} for {path}; "
                "check authentication, event dependencies, and schema"
            )
        return response

    def enqueue(self, batch):
        batch = Batch.model_validate(batch)
        if len(batch_body(batch)) > MAX_BATCH_BYTES:
            raise ValueError(
                f"Atomic batch exceeds the {MAX_BATCH_BYTES}-byte collector limit; "
                "form smaller batches before enqueueing"
            )
        with (self.directory / "queue.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            files = sorted(self.directory.glob("*.json"))
            if len(files) >= 1000:
                raise DeliveryError(
                    f"Outbox is full at {self.directory}; flush it before collecting more"
                )
            sequence = int(files[-1].stem) + 1 if files else 1
            destination = self.directory / f"{sequence:020d}.json"
            temporary = self.directory / f".pending-{uuid4()}.tmp"
            body = batch.model_dump_json(indent=2)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as file:
                file.write(body)
                file.flush()
                os.fsync(file.fileno())
            temporary.replace(destination)
            self.sync_directory()
        return destination

    def sync_directory(self):
        descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def flush(self):
        delivered = 0
        with (self.directory / "queue.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            for file in sorted(self.directory.glob("*.json")):
                batch = Batch.model_validate_json(file.read_text())
                try:
                    response = self.request("POST", "/api/events", content=batch_body(batch))
                    acknowledgment = response.json()
                    committed = set(acknowledgment.get("accepted", [])) | set(
                        acknowledgment.get("duplicates", [])
                    )
                    if committed != {event.event_id for event in batch.events}:
                        raise DeliveryError("Collector did not acknowledge every event ID")
                except (
                    httpx.HTTPError,
                    DeliveryError,
                    ValueError,
                    AttributeError,
                    TypeError,
                ) as exc:
                    log.warning("delivery_pending file=%s reason=%s", file, exc)
                    raise DeliveryError(
                        f"Unsent data remains at {file}. Fix delivery and run flush."
                    ) from exc
                file.unlink()
                self.sync_directory()
                delivered += 1
        return {
            "delivered_batches": delivered,
            "pending_batches": len(list(self.directory.glob("*.json"))),
        }

    def send(self, batch, queue_only=False):
        path = self.enqueue(batch)
        if queue_only:
            return {"queued": str(path)}
        return self.flush()

    def best_effort(self, batch):
        # The only fallback is explicit durable storage, with a warning from flush.
        # Enqueue errors propagate: there is no safe substitute for a durable write.
        self.enqueue(batch)
        try:
            return self.flush()
        except DeliveryError:
            return {"pending": True, "directory": str(self.directory)}
