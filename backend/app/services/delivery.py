import hashlib
import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..config import Settings
from ..database import SessionLocal
from ..models import Batch, DeliveryAttempt, DeliveryStatus, Participant, SendRecord
from .rendering import is_render_current
from .smtp import DefiniteSendError, SMTPClient, TransientSendError, UncertainSendError
from .templates import render_template

logger = logging.getLogger("certificate.delivery")


class SendPaused(Exception):
    """The batch was paused before this message entered SMTP submission."""


def _record_ref(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


class DeliveryManager:
    def __init__(self, settings: Settings, smtp_factory):
        self.settings = settings
        self.smtp_factory = smtp_factory
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._limit_lock = threading.Lock()
        self._rate_lock = threading.Lock()
        self._last_send = 0.0
        self._current_interval = max(
            settings.min_email_send_delay_seconds, settings.email_send_delay_seconds
        )
        self._healthy_streak = 0

    def recover(self) -> int:
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            rows = list(
                db.participants.find(
                    {
                        "status": {
                            "$in": [
                                DeliveryStatus.SENDING.value,
                                str(DeliveryStatus.SENDING),
                                "SENDING",
                            ]
                        }
                    }
                )
            )
            sending_ids = {row["_id"] for row in rows}
            for row in rows:
                p_id = row["_id"]
                err = "Backend restarted while this send was in progress; verify manually before retrying"
                db.participants.update_one(
                    {"_id": p_id},
                    {
                        "$set": {
                            "status": DeliveryStatus.UNCERTAIN.value,
                            "error_reason": err,
                            "updated_at": now,
                        }
                    },
                )
                if row.get("batch_id"):
                    db.batches.update_one(
                        {"_id": row["batch_id"]},
                        {"$set": {"is_paused": True, "updated_at": now}},
                    )
                attempt = db.delivery_attempts.find_one(
                    {"participant_id": p_id, "outcome": None},
                    sort=[("attempt_number", -1)],
                )
                if attempt:
                    db.delivery_attempts.update_one(
                        {"_id": attempt["_id"]},
                        {
                            "$set": {
                                "outcome": "UNCERTAIN",
                                "error_code": "BACKEND_RESTART",
                                "error_reason": err,
                                "finished_at": now,
                            }
                        },
                    )

            reservations = list(db.send_records.find({"status": "RESERVED"}))
            for reservation in reservations:
                uncertain = reservation.get("participant_id") in sending_ids
                res_err = (
                    "Backend restarted during an active SMTP submission"
                    if uncertain
                    else "Backend restarted before SMTP submission"
                )
                db.send_records.update_one(
                    {"_id": reservation["_id"]},
                    {
                        "$set": {
                            "status": "UNCERTAIN" if uncertain else "CANCELLED",
                            "counts_against_limit": uncertain,
                            "finished_at": now,
                            "error_reason": res_err,
                        }
                    },
                )
            if rows or reservations:
                logger.warning(
                    "delivery_event=recovered sending=%s reservations=%s action=marked_uncertain",
                    len(rows),
                    len(reservations),
                )
            return len(rows)

    def is_running(self, batch_id: str) -> bool:
        with self._lock:
            thread = self._threads.get(batch_id)
            return bool(thread and thread.is_alive())

    def allowance(self) -> dict[str, int | bool | None | str]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        with SessionLocal() as db:
            pipeline = [
                {"$match": {"reserved_at": {"$gte": cutoff}}},
                {
                    "$group": {
                        "_id": None,
                        "used": {
                            "$sum": {
                                "$cond": [
                                    {"$eq": ["$counts_against_limit", True]},
                                    1,
                                    0,
                                ]
                            }
                        },
                        "successful": {
                            "$sum": {"$cond": [{"$eq": ["$status", "SENT"]}, 1, 0]}
                        },
                        "failed": {
                            "$sum": {"$cond": [{"$eq": ["$status", "FAILED"]}, 1, 0]}
                        },
                        "uncertain": {
                            "$sum": {
                                "$cond": [{"$eq": ["$status", "UNCERTAIN"]}, 1, 0]
                            }
                        },
                    }
                },
            ]
            res = list(db.send_records.aggregate(pipeline))
            if res:
                used = res[0].get("used", 0)
                successful = res[0].get("successful", 0)
                failed = res[0].get("failed", 0)
                uncertain = res[0].get("uncertain", 0)
            else:
                used = successful = failed = uncertain = 0

        limit = self.settings.max_emails_per_day
        return {
            "enabled": limit is not None,
            "limit": limit,
            "used": used,
            "remaining": max(0, limit - used) if limit is not None else None,
            "successful": successful,
            "failed": failed,
            "uncertain": uncertain,
            "notice": (
                "Email sending limits depend on your SMTP provider, account type, and current provider restrictions. "
                "The application monitors sending activity but cannot guarantee the provider's remaining allowance."
            ),
        }

    def reserve_send(
        self, batch_id: str | None, participant_id: str | None, kind: str
    ) -> str | None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        with self._limit_lock, SessionLocal() as db:
            used = db.send_records.count_documents(
                {"reserved_at": {"$gte": cutoff}, "counts_against_limit": True}
            )
            limit = self.settings.max_emails_per_day
            if limit is not None and used >= limit:
                return None
            record = SendRecord(
                batch_id=batch_id, participant_id=participant_id, kind=kind
            )
            db.send_records.insert_one(record.to_doc())
            return record.id

    def finish_reservation(
        self,
        record_id: str,
        status: str,
        message_id: str | None = None,
        error: str | None = None,
    ):
        with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            counts = status in {"RESERVED", "SENT", "UNCERTAIN"}
            db.send_records.update_one(
                {"_id": record_id},
                {
                    "$set": {
                        "status": status,
                        "finished_at": now,
                        "smtp_message_id": message_id,
                        "error_reason": error,
                        "counts_against_limit": counts,
                    }
                },
            )

    def start(self, batch_id: str) -> bool:
        with self._lock:
            existing = self._threads.get(batch_id)
            if existing and existing.is_alive():
                return False
            thread = threading.Thread(
                target=self._run,
                args=(batch_id,),
                daemon=True,
                name=f"delivery-{batch_id[:8]}",
            )
            self._threads[batch_id] = thread
            thread.start()
            logger.info("delivery_event=worker_started batch=%s", _record_ref(batch_id))
            return True

    @contextmanager
    def submission_slot(self):
        """Serialize SMTP submissions and pace their start times."""
        with self._rate_lock:
            wait = self._last_send + self._current_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_send = time.monotonic()
            yield

    def record_healthy_send(self) -> None:
        with self._rate_lock:
            self._healthy_streak += 1
            if self._healthy_streak >= max(
                1, self.settings.healthy_sends_before_speedup
            ):
                self._current_interval = max(
                    self.settings.min_email_send_delay_seconds,
                    self._current_interval - 0.5,
                )
                self._healthy_streak = 0

    def record_temporary_failure(self, retry_after: int | None = None) -> None:
        with self._rate_lock:
            self._healthy_streak = 0
            increased = max(self._current_interval * 2, float(retry_after or 0))
            self._current_interval = min(
                self.settings.max_email_send_delay_seconds, increased
            )

    def _run(self, batch_id: str):
        with SessionLocal() as db:
            batch_doc = db.batches.find_one({"_id": batch_id})
            if not batch_doc or not batch_doc.get("send_confirmed"):
                return
            batch = Batch.from_doc(batch_doc)
            rows = list(
                db.participants.find(
                    {
                        "batch_id": batch_id,
                        "is_current_import": True,
                        "status": {
                            "$in": [
                                DeliveryStatus.PENDING.value,
                                str(DeliveryStatus.PENDING),
                                "PENDING",
                            ]
                        },
                        "is_valid": True,
                        "is_excluded": False,
                        "certificate_path": {"$ne": None},
                    }
                )
            )
            ids = [
                r["_id"]
                for r in rows
                if r.get("certificate_revision") == batch.certificate_revision
                and is_render_current(r.get("certificate_path"))
            ]
        logger.info(
            "delivery_event=batch_ready batch=%s recipients=%s workers=%s",
            _record_ref(batch_id),
            len(ids),
            self.settings.smtp_workers,
        )
        client = None
        try:
            client = self.smtp_factory()
            for participant_id in ids:
                with SessionLocal() as db:
                    current = db.batches.find_one({"_id": batch_id})
                    if not current or current.get("is_paused"):
                        break
                try:
                    self._send_one(batch_id, participant_id, client)
                except Exception:
                    # _send_one persists all expected failures; a guard below catches programming faults.
                    logger.exception(
                        "delivery_event=unexpected_worker_error participant=%s",
                        _record_ref(participant_id),
                    )
                    with SessionLocal() as db:
                        now = datetime.now(timezone.utc)
                        row = db.participants.find_one({"_id": participant_id})
                        if row and row.get("status") in (
                            DeliveryStatus.SENDING.value,
                            "SENDING",
                        ):
                            err = "Unexpected worker interruption; outcome requires review"
                            db.participants.update_one(
                                {"_id": participant_id},
                                {
                                    "$set": {
                                        "status": DeliveryStatus.UNCERTAIN.value,
                                        "error_reason": err,
                                        "updated_at": now,
                                    }
                                },
                            )
                            reservation = db.send_records.find_one(
                                {
                                    "participant_id": participant_id,
                                    "status": "RESERVED",
                                },
                                sort=[("reserved_at", -1)],
                            )
                            if reservation:
                                db.send_records.update_one(
                                    {"_id": reservation["_id"]},
                                    {
                                        "$set": {
                                            "status": "UNCERTAIN",
                                            "finished_at": now,
                                            "error_reason": err,
                                        }
                                    },
                                )
                            attempt = db.delivery_attempts.find_one(
                                {
                                    "participant_id": participant_id,
                                    "outcome": None,
                                },
                                sort=[("attempt_number", -1)],
                            )
                            if attempt:
                                db.delivery_attempts.update_one(
                                    {"_id": attempt["_id"]},
                                    {
                                        "$set": {
                                            "outcome": "UNCERTAIN",
                                            "error_code": "WORKER_INTERRUPTION",
                                            "error_reason": err,
                                            "finished_at": now,
                                        }
                                    },
                                )
        finally:
            if client and hasattr(client, "close"):
                client.close()
            with SessionLocal() as db:
                batch_doc = db.batches.find_one({"_id": batch_id})
                if batch_doc and not batch_doc.get("is_paused"):
                    db.batches.update_one(
                        {"_id": batch_id},
                        {"$set": {"send_job_finished_at": datetime.now(timezone.utc)}},
                    )
            logger.info("delivery_event=worker_stopped batch=%s", _record_ref(batch_id))

    def _send_one(
        self,
        batch_id: str,
        participant_id: str,
        client: SMTPClient | None = None,
    ):
        attempt_started = time.perf_counter()
        with SessionLocal() as db:
            batch_doc = db.batches.find_one({"_id": batch_id})
            participant_doc = db.participants.find_one({"_id": participant_id})
            if (
                not batch_doc
                or not participant_doc
                or batch_doc.get("is_paused")
                or participant_doc.get("status")
                not in (DeliveryStatus.PENDING.value, "PENDING")
            ):
                return
            batch = Batch.from_doc(batch_doc)
            participant = Participant.from_doc(participant_doc)
            if not batch.sender_email or not participant.certificate_path:
                db.participants.update_one(
                    {"_id": participant_id},
                    {
                        "$set": {
                            "status": DeliveryStatus.FAILED.value,
                            "error_reason": "Email configuration or certificate is missing",
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                )
                return
            if participant.certificate_revision != batch.certificate_revision or not is_render_current(
                participant.certificate_path
            ):
                db.participants.update_one(
                    {"_id": participant_id},
                    {
                        "$set": {
                            "error_reason": "Certificate styling changed; regenerate before sending",
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                )
                logger.warning(
                    "delivery_event=skipped participant=%s reason=outdated_certificate",
                    _record_ref(participant_id),
                )
                return
            name, email, key = (
                participant.name,
                participant.email,
                participant.idempotency_key,
            )
            sender, path = batch.sender_email, Path(participant.certificate_path)
            values = {
                "name": name,
                "certificate_id": participant.certificate_code or "",
                "certificate_code": participant.certificate_code or "",
            }
            subject = render_template(batch.email_subject, values)
            body = render_template(batch.email_body, values)
        logger.info(
            "delivery_event=profile participant=%s stage=prepare duration_ms=%s",
            _record_ref(participant_id),
            round((time.perf_counter() - attempt_started) * 1000, 1),
        )

        reservation_started = time.perf_counter()
        reservation_id = self.reserve_send(batch_id, participant_id, "BULK")
        if not reservation_id:
            with SessionLocal() as db:
                p = db.participants.find_one({"_id": participant_id})
                if p and p.get("status") in (
                    DeliveryStatus.PENDING.value,
                    "PENDING",
                ):
                    db.participants.update_one(
                        {"_id": participant_id},
                        {
                            "$set": {
                                "error_reason": "Rolling 24-hour application sending limit reached",
                                "updated_at": datetime.now(timezone.utc),
                            }
                        },
                    )
                    db.batches.update_one(
                        {"_id": batch_id},
                        {"$set": {"is_paused": True, "updated_at": datetime.now(timezone.utc)}},
                    )
            return
        logger.info(
            "delivery_event=profile participant=%s stage=quota_reservation duration_ms=%s",
            _record_ref(participant_id),
            round((time.perf_counter() - reservation_started) * 1000, 1),
        )

        claim_started = time.perf_counter()
        with SessionLocal() as db:
            batch_doc = db.batches.find_one({"_id": batch_id})
            if not batch_doc or batch_doc.get("is_paused"):
                self.finish_reservation(
                    reservation_id,
                    "CANCELLED",
                    error="Send cancelled before SMTP submission",
                )
                return
            claimed = db.participants.find_one_and_update(
                {
                    "_id": participant_id,
                    "status": {
                        "$in": [
                            DeliveryStatus.PENDING.value,
                            str(DeliveryStatus.PENDING),
                            "PENDING",
                        ]
                    },
                },
                {
                    "$set": {
                        "status": DeliveryStatus.SENDING.value,
                        "error_reason": None,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
                return_document=True,
            )
            if not claimed:
                self.finish_reservation(
                    reservation_id,
                    "CANCELLED",
                    error="Participant was already claimed",
                )
                return
            attempt_count = db.delivery_attempts.count_documents(
                {"participant_id": participant_id}
            )
            attempt = DeliveryAttempt(
                participant_id=participant_id,
                attempt_number=attempt_count + 1,
                certificate_path=claimed.get("certificate_path"),
                certificate_filename=claimed.get("filename"),
            )
            db.delivery_attempts.insert_one(attempt.to_doc())
        logger.info(
            "delivery_event=profile participant=%s stage=atomic_claim duration_ms=%s",
            _record_ref(participant_id),
            round((time.perf_counter() - claim_started) * 1000, 1),
        )
        logger.info(
            "delivery_event=status participant=%s status=SENDING",
            _record_ref(participant_id),
        )

        try:
            client = client or self.smtp_factory()
        except Exception:
            with SessionLocal() as db:
                now = datetime.now(timezone.utc)
                db.participants.update_one(
                    {"_id": participant_id},
                    {
                        "$set": {
                            "status": DeliveryStatus.FAILED.value,
                            "error_reason": "SMTP backend configuration is unavailable",
                            "updated_at": now,
                        }
                    },
                )
                attempt = db.delivery_attempts.find_one(
                    {"participant_id": participant_id},
                    sort=[("attempt_number", -1)],
                )
                if attempt:
                    db.delivery_attempts.update_one(
                        {"_id": attempt["_id"]},
                        {
                            "$set": {
                                "outcome": "FAILED",
                                "error_code": "SMTP_CONFIGURATION",
                                "error_reason": "SMTP backend configuration is unavailable",
                                "finished_at": now,
                            }
                        },
                    )
            self.finish_reservation(
                reservation_id,
                "FAILED",
                error="SMTP backend configuration is unavailable",
            )
            return

        last_error: Exception | None = None
        for retry in range(3):
            try:
                with self.submission_slot():
                    with SessionLocal() as db:
                        current_batch = db.batches.find_one({"_id": batch_id})
                        if not current_batch or current_batch.get("is_paused"):
                            raise SendPaused()
                    smtp_started = time.perf_counter()
                    message_id = client.send(
                        sender, email, subject, body, path, key
                    )
                smtp_duration = time.perf_counter() - smtp_started
                self.record_healthy_send()
                persist_started = time.perf_counter()
                with SessionLocal() as db:
                    now = datetime.now(timezone.utc)
                    db.participants.update_one(
                        {"_id": participant_id},
                        {
                            "$set": {
                                "status": DeliveryStatus.SENT.value,
                                "smtp_message_id": message_id,
                                "sent_at": now,
                                "updated_at": now,
                            }
                        },
                    )
                    attempt = db.delivery_attempts.find_one(
                        {"participant_id": participant_id},
                        sort=[("attempt_number", -1)],
                    )
                    if attempt:
                        db.delivery_attempts.update_one(
                            {"_id": attempt["_id"]},
                            {
                                "$set": {
                                    "outcome": "SENT",
                                    "smtp_message_id": message_id,
                                    "finished_at": now,
                                }
                            },
                        )
                self.finish_reservation(
                    reservation_id, "SENT", message_id=message_id
                )
                logger.info(
                    "delivery_event=status participant=%s status=SENT smtp_ms=%s persist_ms=%s total_ms=%s",
                    _record_ref(participant_id),
                    round(smtp_duration * 1000, 1),
                    round((time.perf_counter() - persist_started) * 1000, 1),
                    round((time.perf_counter() - attempt_started) * 1000, 1),
                )
                return
            except TransientSendError as exc:
                last_error = exc
                self.record_temporary_failure(exc.retry_after)
                logger.warning(
                    "delivery_event=transient participant=%s retry=%s",
                    _record_ref(participant_id),
                    retry + 1,
                )
                if exc.rate_limited:
                    with SessionLocal() as db:
                        db.batches.update_one(
                            {"_id": batch_id},
                            {"$set": {"is_paused": True, "updated_at": datetime.now(timezone.utc)}},
                        )
                    logger.warning(
                        "delivery_event=batch_paused batch=%s reason=rate_limit code=%s",
                        _record_ref(batch_id),
                        exc.smtp_code,
                    )
                    break
                if retry < 2:
                    time.sleep(exc.retry_after or 2**retry)
                    continue
            except (DefiniteSendError, UncertainSendError) as exc:
                last_error = exc
            except SendPaused:
                with SessionLocal() as db:
                    now = datetime.now(timezone.utc)
                    p = db.participants.find_one({"_id": participant_id})
                    if p and p.get("status") in (
                        DeliveryStatus.SENDING.value,
                        "SENDING",
                    ):
                        db.participants.update_one(
                            {"_id": participant_id},
                            {
                                "$set": {
                                    "status": DeliveryStatus.PENDING.value,
                                    "error_reason": "Sending paused before SMTP submission",
                                    "updated_at": now,
                                }
                            },
                        )
                    attempt = db.delivery_attempts.find_one(
                        {"participant_id": participant_id},
                        sort=[("attempt_number", -1)],
                    )
                    if attempt:
                        db.delivery_attempts.update_one(
                            {"_id": attempt["_id"]},
                            {
                                "$set": {
                                    "outcome": "PAUSED",
                                    "error_code": "PAUSED",
                                    "finished_at": now,
                                }
                            },
                        )
                self.finish_reservation(
                    reservation_id,
                    "CANCELLED",
                    error="Sending paused before SMTP submission",
                )
                logger.info(
                    "delivery_event=status participant=%s status=PENDING reason=paused",
                    _record_ref(participant_id),
                )
                return
            break

        with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            uncertain = isinstance(last_error, UncertainSendError)
            final_status = (
                DeliveryStatus.UNCERTAIN.value
                if uncertain
                else DeliveryStatus.FAILED.value
            )
            db.participants.update_one(
                {"_id": participant_id},
                {
                    "$set": {
                        "status": final_status,
                        "error_reason": str(last_error),
                        "updated_at": now,
                    }
                },
            )
            attempt = db.delivery_attempts.find_one(
                {"participant_id": participant_id},
                sort=[("attempt_number", -1)],
            )
            if attempt:
                db.delivery_attempts.update_one(
                    {"_id": attempt["_id"]},
                    {
                        "$set": {
                            "outcome": final_status,
                            "error_code": (
                                "UNCERTAIN_SUBMISSION"
                                if uncertain
                                else "DEFINITE_FAILURE"
                            ),
                            "error_reason": str(last_error),
                            "finished_at": now,
                        }
                    },
                )
        self.finish_reservation(
            reservation_id,
            "UNCERTAIN" if uncertain else "FAILED",
            error=str(last_error),
        )
        logger.warning(
            "delivery_event=status participant=%s status=%s",
            _record_ref(participant_id),
            "UNCERTAIN" if uncertain else "FAILED",
        )
