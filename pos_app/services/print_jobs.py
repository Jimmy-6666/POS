import secrets
import threading
import time

from flask import current_app, url_for


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
        return None
    return current_app.extensions["print_jobs"].enqueue(document_type, entity_id)


def claim_print():
    job = current_app.extensions["print_jobs"].claim()
    if not job:
        return None
    job["render_url"] = url_for("print_agent.render_job", job_id=job["id"])
    return job


def get_print_job(job_id):
    return current_app.extensions["print_jobs"].get(job_id)


def acknowledge_print(job_id):
    return current_app.extensions["print_jobs"].acknowledge(job_id)
