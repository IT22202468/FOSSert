import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..config import Settings
from ..database import SessionLocal
from ..models import Batch
from .fonts import resolve_font_path
from .rendering import render_certificate

logger = logging.getLogger("certificate.generation")


class GenerationManager:
    """Runs one durable, observable certificate-generation job per batch."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def recover(self) -> int:
        with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            res = db.batches.update_many(
                {"generation_status": "RUNNING"},
                {
                    "$set": {
                        "generation_status": "INTERRUPTED",
                        "generation_current_name": None,
                        "generation_finished_at": now,
                    }
                },
            )
            return res.modified_count

    def is_running(self, batch_id: str) -> bool:
        with self._lock:
            thread = self._threads.get(batch_id)
            return bool(thread and thread.is_alive())

    def start(self, batch_id: str, participant_id: str | None = None) -> bool:
        with self._lock:
            existing = self._threads.get(batch_id)
            if existing and existing.is_alive():
                return False
            thread = threading.Thread(
                target=self._run,
                args=(batch_id, participant_id),
                daemon=True,
                name=f"generation-{batch_id[:8]}",
            )
            self._threads[batch_id] = thread
            thread.start()
            return True

    def _run(self, batch_id: str, participant_id: str | None = None) -> None:
        job_id = str(uuid.uuid4())
        with SessionLocal() as db:
            batch_doc = db.batches.find_one({"_id": batch_id})
            if not batch_doc or not batch_doc.get("template_path"):
                return
            batch = Batch.from_doc(batch_doc)
            active_import_id = batch.active_import_id
            query = {
                "batch_id": batch_id,
                "is_current_import": True,
                "is_valid": True,
                "is_excluded": False,
            }
            if participant_id:
                query["_id"] = participant_id

            rows = list(db.participants.find(query).sort("row_number", 1))
            ids = [r["_id"] for r in rows]
            now = datetime.now(timezone.utc)
            db.batches.update_one(
                {"_id": batch_id},
                {
                    "$set": {
                        "generation_job_id": job_id,
                        "generation_status": "RUNNING",
                        "generation_total": len(ids),
                        "generation_succeeded": 0,
                        "generation_failed": 0,
                        "generation_current_name": None,
                        "generation_started_at": now,
                        "generation_finished_at": None,
                    }
                },
            )
            template_path = Path(batch.template_path)
            font_path = resolve_font_path(batch.font_path)
            certificate_revision = batch.certificate_revision
            region = {
                "x": batch.region_x,
                "y": batch.region_y,
                "w": batch.region_w,
                "h": batch.region_h,
                "font_size": batch.font_size,
                "min_font_size": batch.min_font_size,
                "auto_fit": batch.auto_fit,
                "vertical_offset": batch.vertical_offset,
            }

        output = self.settings.generated_dir / batch_id
        for pid in ids:
            with SessionLocal() as db:
                batch_doc = db.batches.find_one({"_id": batch_id})
                row_doc = db.participants.find_one({"_id": pid})
                if not batch_doc or batch_doc.get("generation_job_id") != job_id:
                    return
                # An import/edit during a job cannot attach an old result to the
                # replacement dataset. The endpoint blocks those mutations, and
                # this check is a final integrity guard.
                if (
                    not row_doc
                    or not row_doc.get("is_current_import")
                    or row_doc.get("import_id") != active_import_id
                ):
                    db.batches.update_one({"_id": batch_id}, {"$inc": {"generation_failed": 1}})
                    continue
                db.batches.update_one(
                    {"_id": batch_id},
                    {"$set": {"generation_current_name": row_doc.get("name")}},
                )
                db.participants.update_one({"_id": pid}, {"$set": {"generation_error": None}})
                name = row_doc.get("name")
                code = row_doc.get("certificate_code")

            try:
                result = render_certificate(
                    template_path,
                    font_path,
                    output,
                    pid,
                    name,
                    region,
                    certificate_code=code,
                )
                with SessionLocal() as db:
                    batch_doc = db.batches.find_one({"_id": batch_id})
                    row_doc = db.participants.find_one({"_id": pid})
                    if (
                        not batch_doc
                        or batch_doc.get("generation_job_id") != job_id
                        or not row_doc
                        or not row_doc.get("is_current_import")
                        or row_doc.get("import_id") != active_import_id
                    ):
                        continue
                    db.participants.update_one(
                        {"_id": pid},
                        {
                            "$set": {
                                "certificate_path": str(result.pdf_path.resolve()),
                                "preview_path": str(result.preview_path.resolve()),
                                "filename": result.filename,
                                "legibility_warning": result.warning,
                                "generation_error": None,
                                "certificate_revision": certificate_revision,
                            }
                        },
                    )
                    db.batches.update_one(
                        {"_id": batch_id}, {"$inc": {"generation_succeeded": 1}}
                    )
            except Exception as exc:  # preserve the rest of a bulk generation job
                logger.exception("certificate generation failed participant=%s", pid[:12])
                with SessionLocal() as db:
                    batch_doc = db.batches.find_one({"_id": batch_id})
                    if not batch_doc or batch_doc.get("generation_job_id") != job_id:
                        return
                    db.participants.update_one(
                        {"_id": pid},
                        {"$set": {"generation_error": f"{type(exc).__name__}: {exc}"}},
                    )
                    db.batches.update_one(
                        {"_id": batch_id}, {"$inc": {"generation_failed": 1}}
                    )

        with SessionLocal() as db:
            batch_doc = db.batches.find_one({"_id": batch_id})
            if batch_doc and batch_doc.get("generation_job_id") == job_id:
                failed = batch_doc.get("generation_failed", 0)
                status = "COMPLETED" if failed == 0 else "COMPLETED_WITH_ERRORS"
                db.batches.update_one(
                    {"_id": batch_id},
                    {
                        "$set": {
                            "generation_status": status,
                            "generation_current_name": None,
                            "generation_finished_at": datetime.now(timezone.utc),
                        }
                    },
                )
