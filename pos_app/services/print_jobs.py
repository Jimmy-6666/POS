import secrets
import threading
import time

from flask import current_app, url_for

from .print_diagnostics import record_print_event


class PrintJobQueue:
    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def enqueue(self, document_type, entity_id):
        job_id = secrets.token_urlsafe(18)
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "document_type": document_type,
                "entity_id": int(entity_id),
                "status": "pending",
                "claimed_at": None,
            }
        return job_id

    def claim(self):
        now = time.monotonic()
        with self._lock:
            for job in self._jobs.values():
                if job["status"] == "pending" or (
                    job["status"] == "claimed" and now - job["claimed_at"] > 30
                ):
                    job["status"] = "claimed"
                    job["claimed_at"] = now
                    return dict(job)
        return None

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def acknowledge(self, job_id):
        with self._lock:
            return self._jobs.pop(job_id, None) is not None


def init_app(app):
    app.extensions["print_jobs"] = PrintJobQueue()


def enqueue_print(document_type, entity_id):
    if not current_app.config.get("PRINT_AGENT_TOKEN"):
        record_print_event(
            "queue_unavailable",
            source="server",
            details={"document_type": document_type, "entity_id": entity_id, "reason": "print-agent-token-missing"},
        )
        return None
    job_id = current_app.extensions["print_jobs"].enqueue(document_type, entity_id)
    record_print_event(
        "queue_created",
        source="server",
        details={"job_id": job_id, "document_type": document_type, "entity_id": entity_id},
    )
    return job_id


def claim_print():
    job = current_app.extensions["print_jobs"].claim()
    if not job:
        return None
    record_print_event(
        "queue_claimed",
        source="server",
        details={"job_id": job["id"], "document_type": job["document_type"], "entity_id": job["entity_id"]},
    )
    job["render_url"] = url_for("print_agent.render_job", job_id=job["id"])
    return job


def get_print_job(job_id):
    return current_app.extensions["print_jobs"].get(job_id)


def acknowledge_print(job_id):
    acknowledged = current_app.extensions["print_jobs"].acknowledge(job_id)
    record_print_event(
        "queue_acknowledged" if acknowledged else "queue_acknowledge_missing",
        source="server",
        details={"job_id": job_id},
    )
    return acknowledged
