import asyncio
import csv
import io
import json
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Security, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from PIL import Image, ImageFont, UnidentifiedImageError

from .config import get_settings
from .database import (
    SessionLocal,
    clean_session_name,
    ensure_schema,
    get_db,
    normalized_session_name,
)
from .models import (
    AdminSession,
    AdminUser,
    Batch,
    DEFAULT_EMAIL_BODY,
    DEFAULT_EMAIL_SUBJECT,
    DeliveryAttempt,
    DeliveryStatus,
    Participant,
    SendRecord,
)
from .schemas import (
    BatchCreate,
    EmailConfig,
    LoginRequest,
    ParticipantPatch,
    PreviewRequest,
    ReconcileRequest,
    RegionUpdate,
    RevokeCertificateRequest,
    StartSendRequest,
)
from .services.auth import (
    create_admin_session,
    get_current_admin,
    get_optional_admin,
    revoke_admin_session,
    security,
    verify_password,
)
from .services.codes import generate_certificate_code
from .services.csv_import import csv_safe, parse_participants, resolve_columns, validate_participant
from .services.delivery import DeliveryManager
from .services.files import safe_filename
from .services.fonts import font_display_name, resolve_font_path
from .services.generation import GenerationManager
from .services.rendering import is_render_current, make_zip, render_preview_png
from .services.smtp import DefiniteSendError, SMTPClient, message_id_for

settings = get_settings()


def smtp_configured() -> bool:
    return bool(settings.smtp_username and settings.smtp_app_password and settings.smtp_sender_email)


def smtp_client() -> SMTPClient:
    if not smtp_configured():
        raise DefiniteSendError("Configure SMTP_USERNAME, SMTP_APP_PASSWORD, and SMTP_SENDER_EMAIL first")
    return SMTPClient(
        settings.smtp_host,
        settings.smtp_port,
        settings.smtp_username or "",
        settings.smtp_app_password or "",
        settings.smtp_sender_email or "",
        settings.smtp_aliases,
        settings.smtp_timeout_seconds,
        data_timeout=settings.smtp_data_timeout_seconds,
        connection_reuse=settings.smtp_connection_reuse,
        max_messages_per_connection=settings.smtp_max_messages_per_connection,
    )


def allowed_senders() -> set[str]:
    if not settings.smtp_sender_email:
        return set()
    return {settings.smtp_sender_email.casefold(), *settings.smtp_aliases}


delivery = DeliveryManager(settings, smtp_client)
generation = GenerationManager(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_schema()
    delivery.recover()
    generation.recover()
    yield


app = FastAPI(title="Certificate Dispatch API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_batch_model(db: Any, batch_id: str, include_attempts: bool = True) -> Batch | None:
    doc = db.batches.find_one({"_id": batch_id})
    if not doc:
        return None
    batch = Batch.from_doc(doc)
    p_docs = list(db.participants.find({"batch_id": batch_id}).sort("row_number", 1))
    participants = []
    if include_attempts and p_docs:
        p_ids = [p["_id"] for p in p_docs]
        att_docs = list(
            db.delivery_attempts.find({"participant_id": {"$in": p_ids}}).sort("attempt_number", 1)
        )
        att_by_p: dict[str, list[DeliveryAttempt]] = {}
        for a in att_docs:
            att_by_p.setdefault(a["participant_id"], []).append(DeliveryAttempt.from_doc(a))
        for p in p_docs:
            part = Participant.from_doc(p)
            part.attempts = att_by_p.get(part.id, [])
            part.batch = batch
            participants.append(part)
    else:
        for p in p_docs:
            part = Participant.from_doc(p)
            part.batch = batch
            participants.append(part)
    batch.participants = participants
    return batch


def batch_or_404(db: Any, batch_id: str) -> Batch:
    batch = get_batch_model(db, batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")
    return batch


def revalidate_active_participants(batch: Batch) -> None:
    """Revalidate the active import as a set so duplicate corrections resolve immediately."""
    seen: set[str] = set()
    for row in sorted((p for p in batch.participants if p.is_current_import), key=lambda item: item.row_number):
        clean_name, canonical, errors = validate_participant(row.name, row.email)
        row.name = clean_name
        row.canonical_email = canonical or None
        if canonical and canonical in seen:
            errors.append("Duplicate email in this import")
        elif canonical:
            seen.add(canonical)
        row.is_valid = not errors
        row.validation_error = "; ".join(errors) or None


def advance_certificate_revision(batch: Batch) -> None:
    batch.certificate_revision = str(uuid.uuid4())


def serialize_batch(batch: Batch, include_participants: bool = True) -> dict:
    counts = {status.value: 0 for status in DeliveryStatus}
    imported = [p for p in batch.participants if p.is_current_import]
    active = [p for p in imported if p.is_valid and not p.is_excluded]
    for participant in active:
        counts[participant.status.value] += 1
    current = {
        p.id: bool(
            p.certificate_revision == batch.certificate_revision
            and is_render_current(p.certificate_path)
        )
        for p in imported
    }
    ready_count = sum(p.status == DeliveryStatus.PENDING and current[p.id] for p in active)
    outdated_count = sum(bool(p.certificate_path) and not current[p.id] for p in active)
    started_at = batch.send_job_started_at
    finished_at = batch.send_job_finished_at
    progress_total = batch.send_job_total or 0
    progress_counts = {"SENT": 0, "FAILED": 0, "UNCERTAIN": 0}
    if started_at:
        with SessionLocal() as progress_db:
            pipeline = [
                {
                    "$match": {
                        "batch_id": batch.id,
                        "kind": "BULK",
                        "reserved_at": {"$gte": started_at},
                    }
                },
                {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            ]
            for item in progress_db.send_records.aggregate(pipeline):
                st = item["_id"]
                if st in progress_counts:
                    progress_counts[st] = item["count"]

    processed = sum(progress_counts.values())
    sending_count = counts[DeliveryStatus.SENDING.value]
    job_pending = max(0, progress_total - processed - sending_count)
    current_recipient = next((p.name for p in active if p.status == DeliveryStatus.SENDING), None)
    end = finished_at or datetime.now(timezone.utc)
    if started_at:
        start = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
        end_aware = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
        elapsed_seconds = max(0, int((end_aware - start).total_seconds()))
    else:
        elapsed_seconds = 0
    eta_seconds = int(elapsed_seconds / processed * job_pending) if processed and job_pending else 0
    invalid_count = sum(not p.is_valid for p in imported)
    duplicate_count = sum(bool(p.validation_error and "Duplicate email" in p.validation_error) for p in imported)
    generation_done = batch.generation_succeeded + batch.generation_failed
    participant_by_id = {participant.id: participant for participant in batch.participants}
    return {
        "id": batch.id,
        "name": batch.name,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "updated_at": batch.updated_at.isoformat() if batch.updated_at else None,
        "template_path": bool(batch.template_path),
        "font_path": bool(batch.font_path),
        "font_name": font_display_name(batch.font_path),
        "uses_custom_font": bool(batch.font_path),
        "sender_email": batch.sender_email,
        "email_subject": batch.email_subject,
        "email_body": batch.email_body,
        "is_paused": batch.is_paused,
        "send_confirmed": batch.send_confirmed,
        "region": {
            "x": batch.region_x,
            "y": batch.region_y,
            "w": batch.region_w,
            "h": batch.region_h,
            "font_size": batch.font_size,
            "min_font_size": batch.min_font_size,
            "auto_fit": batch.auto_fit,
            "vertical_offset": batch.vertical_offset,
        },
        "counts": {"TOTAL": len(active), **counts},
        "ready_count": ready_count,
        "outdated_certificate_count": outdated_count,
        "import_counts": {
            "total": len(imported),
            "valid": len(imported) - invalid_count,
            "invalid": invalid_count,
            "duplicates": duplicate_count,
            "preserved": 0,
        },
        "allowance": delivery.allowance(),
        "generation": {
            "job_id": batch.generation_job_id,
            "status": batch.generation_status,
            "total": batch.generation_total,
            "succeeded": batch.generation_succeeded,
            "failed": batch.generation_failed,
            "remaining": max(0, batch.generation_total - generation_done),
            "percent": (
                round(generation_done / batch.generation_total * 100, 1)
                if batch.generation_total
                else 0
            ),
            "current_name": batch.generation_current_name,
            "started_at": (
                batch.generation_started_at.isoformat()
                if batch.generation_started_at
                else None
            ),
            "finished_at": (
                batch.generation_finished_at.isoformat()
                if batch.generation_finished_at
                else None
            ),
        },
        "progress": {
            "total": progress_total,
            "processed": processed,
            "pending": job_pending,
            "sending": sending_count,
            "sent": progress_counts["SENT"],
            "failed": progress_counts["FAILED"],
            "uncertain": progress_counts["UNCERTAIN"],
            "percent": (
                round(processed / progress_total * 100, 1)
                if progress_total
                else 0
            ),
            "current_recipient": current_recipient,
            "elapsed_seconds": elapsed_seconds,
            "eta_seconds": eta_seconds,
            "started_at": started_at.isoformat() if started_at else None,
            "finished_at": finished_at.isoformat() if finished_at else None,
        },
        "participants": [
            {
                "id": p.id,
                "certificate_code": p.certificate_code,
                "row_number": p.row_number,
                "name": p.name,
                "email": p.email,
                "is_valid": p.is_valid,
                "is_excluded": p.is_excluded,
                "is_revoked": p.is_revoked,
                "revoked_at": p.revoked_at.isoformat() if p.revoked_at else None,
                "revocation_reason": p.revocation_reason,
                "validation_error": p.validation_error,
                "status": p.status.value,
                "filename": p.filename,
                "certificate_current": current[p.id],
                "legibility_warning": p.legibility_warning,
                "generation_error": p.generation_error,
                "smtp_message_id": p.smtp_message_id,
                "sent_at": p.sent_at.isoformat() if p.sent_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                "error_reason": p.error_reason,
                "delivery_reference": p.idempotency_key,
                "previous_delivery": (
                    {
                        "participant_id": p.previous_delivery_id,
                        "name": participant_by_id[p.previous_delivery_id].name,
                        "email": participant_by_id[p.previous_delivery_id].email,
                        "sent_at": (
                            participant_by_id[p.previous_delivery_id].sent_at.isoformat()
                            if participant_by_id[p.previous_delivery_id].sent_at
                            else None
                        ),
                        "smtp_message_id": participant_by_id[p.previous_delivery_id].smtp_message_id,
                        "filename": participant_by_id[p.previous_delivery_id].filename,
                    }
                    if p.previous_delivery_id and p.previous_delivery_id in participant_by_id
                    else None
                ),
                "attempts": [
                    {
                        "attempt_number": a.attempt_number,
                        "started_at": a.started_at.isoformat() if a.started_at else None,
                        "finished_at": a.finished_at.isoformat() if a.finished_at else None,
                        "outcome": a.outcome,
                        "error_code": a.error_code,
                        "error_reason": a.error_reason,
                        "reconciliation_action": a.reconciliation_action,
                        "reconciliation_note": a.reconciliation_note,
                        "reconciled_at": a.reconciled_at.isoformat() if a.reconciled_at else None,
                        "certificate_filename": a.certificate_filename,
                    }
                    for a in sorted(p.attempts, key=lambda item: item.attempt_number, reverse=True)
                ],
            }
            for p in sorted(imported, key=lambda item: item.row_number)
        ]
        if include_participants
        else [],
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(payload: LoginRequest, db: Any = Depends(get_db)):
    user_doc = db.admin_users.find_one({"username": payload.username.strip()})
    if not user_doc:
        raise HTTPException(401, "Invalid username or password")
    user = AdminUser.from_doc(user_doc)
    if not verify_password(payload.password, user.password_hash, user.salt):
        raise HTTPException(401, "Invalid username or password")
    token, expires_at = create_admin_session(db, user, duration_hours=settings.auth_session_hours)
    return {
        "token": token,
        "username": user.username,
        "expires_at": expires_at.isoformat(),
    }


@app.post("/api/auth/logout")
def logout(
    credentials=Security(security),
    db: Any = Depends(get_db),
):
    if credentials and getattr(credentials, "credentials", None):
        revoke_admin_session(db, credentials.credentials.strip())
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(admin: AdminUser = Depends(get_current_admin)):
    return {"authenticated": True, "username": admin.username}


@app.get("/api/verify/{certificate_code}")
def verify_certificate(certificate_code: str, db: Any = Depends(get_db)):
    clean_code = certificate_code.strip()
    escaped_code = re.escape(clean_code)
    p_doc = db.participants.find_one({"certificate_code": {"$regex": f"^{escaped_code}$", "$options": "i"}})
    if not p_doc:
        raise HTTPException(404, "Certificate not found")

    participant = Participant.from_doc(p_doc)
    batch_doc = db.batches.find_one({"_id": participant.batch_id}) if participant.batch_id else None
    workshop_name = batch_doc.get("name") if batch_doc else "SLIIT FOSS Workshop"

    has_pdf = bool(participant.certificate_path and Path(participant.certificate_path).exists())
    has_preview = bool(participant.preview_path and Path(participant.preview_path).exists())
    issue_date = participant.sent_at or participant.updated_at

    return {
        "found": True,
        "certificate_code": participant.certificate_code,
        "recipient_name": participant.name,
        "workshop_name": workshop_name,
        "issuer": "SLIIT FOSS Community",
        "issue_date": issue_date.isoformat() if issue_date else None,
        "status": (
            "REVOKED"
            if participant.is_revoked
            else (
                "ISSUED"
                if participant.status == DeliveryStatus.SENT
                else ("GENERATED" if participant.filename else participant.status.value)
            )
        ),
        "verified": not participant.is_revoked,
        "is_revoked": bool(participant.is_revoked),
        "revoked_at": participant.revoked_at.isoformat() if participant.revoked_at else None,
        "revocation_reason": participant.revocation_reason if participant.is_revoked else None,
        "has_pdf": has_pdf and not participant.is_revoked,
        "has_preview": has_preview and not participant.is_revoked,
    }


@app.get("/api/verify/{certificate_code}/preview")
def verify_preview(certificate_code: str, db: Any = Depends(get_db)):
    clean_code = certificate_code.strip()
    escaped_code = re.escape(clean_code)
    p_doc = db.participants.find_one({"certificate_code": {"$regex": f"^{escaped_code}$", "$options": "i"}})
    if not p_doc or not p_doc.get("preview_path") or not Path(p_doc["preview_path"]).exists():
        raise HTTPException(404, "Certificate preview not available")
    if p_doc.get("is_revoked"):
        raise HTTPException(410, "This certificate has been revoked and preview is unavailable")
    return FileResponse(p_doc["preview_path"], media_type="image/png")


@app.get("/api/verify/{certificate_code}/download")
def verify_download(certificate_code: str, db: Any = Depends(get_db)):
    clean_code = certificate_code.strip()
    escaped_code = re.escape(clean_code)
    p_doc = db.participants.find_one({"certificate_code": {"$regex": f"^{escaped_code}$", "$options": "i"}})
    if not p_doc or not p_doc.get("certificate_path") or not Path(p_doc["certificate_path"]).exists():
        raise HTTPException(404, "Certificate PDF not available")
    if p_doc.get("is_revoked"):
        raise HTTPException(410, "This certificate has been revoked by the issuing authority and cannot be downloaded")
    return FileResponse(
        p_doc["certificate_path"],
        media_type="application/pdf",
        filename=p_doc.get("filename") or f"certificate-{p_doc.get('certificate_code')}.pdf",
    )


@app.post("/api/batches", dependencies=[Depends(get_current_admin)])
def create_batch(payload: BatchCreate, db: Any = Depends(get_db)):
    name = clean_session_name(payload.name)
    normalized = normalized_session_name(name)
    existing = db.batches.find_one({"name_normalized": normalized})
    if existing:
        raise HTTPException(409, f'A session named "{name}" already exists')

    now = datetime.now(timezone.utc)
    batch = Batch(
        name=name,
        name_normalized=normalized,
        email_subject=DEFAULT_EMAIL_SUBJECT,
        email_body=DEFAULT_EMAIL_BODY,
        created_at=now,
        updated_at=now,
    )
    db.batches.insert_one(batch.to_doc())
    batch.participants = []
    return serialize_batch(batch)


@app.get("/api/batches", dependencies=[Depends(get_current_admin)])
def list_batches(db: Any = Depends(get_db)):
    res = []
    for doc in db.batches.find().sort("created_at", -1):
        batch = get_batch_model(db, doc["_id"], include_attempts=False)
        if batch:
            res.append(serialize_batch(batch, False))
    return res


@app.get("/api/batches/{batch_id}", dependencies=[Depends(get_current_admin)])
def get_batch(batch_id: str, db: Any = Depends(get_db)):
    return serialize_batch(batch_or_404(db, batch_id))


async def read_limited(file: UploadFile) -> bytes:
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB")
    return data


@app.post("/api/batches/{batch_id}/participants/import", dependencies=[Depends(get_current_admin)])
async def import_csv(
    batch_id: str,
    file: UploadFile = File(...),
    name_column: str | None = Form(None),
    email_column: str | None = Form(None),
    confirm_replace: bool = Form(False),
    db: Any = Depends(get_db),
):
    batch = batch_or_404(db, batch_id)
    if generation.is_running(batch_id) or batch.generation_status == "RUNNING":
        raise HTTPException(409, "Wait for certificate generation to finish before replacing the participant list")
    if delivery.is_running(batch_id) or any(p.status == DeliveryStatus.SENDING for p in batch.participants):
        raise HTTPException(409, "Pause sending and wait for the current SMTP submission to finish before importing a new CSV")
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "Only .csv files are accepted")
    data = await read_limited(file)
    try:
        rows, headers = parse_participants(data, name_column, email_column)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    resolved_name, resolved_email = resolve_columns(headers, name_column, email_column)
    if not resolved_name or not resolved_email:
        raise HTTPException(
            422,
            {
                "code": "column_mapping_required",
                "message": "We could not identify both participant columns. Choose the Name and Email columns below.",
                "headers": headers,
                "detected": {"name": resolved_name, "email": resolved_email},
            },
        )
    if not rows:
        raise HTTPException(422, "The CSV has headers but contains no participant rows")
    current_rows = [participant for participant in batch.participants if participant.is_current_import]
    replacement_has_history = any(
        participant.certificate_path or participant.attempts or participant.status != DeliveryStatus.PENDING
        for participant in current_rows
    ) or bool(batch.send_job_total or batch.send_job_started_at)
    if current_rows and replacement_has_history and not confirm_replace:
        raise HTTPException(
            409,
            {
                "code": "replace_confirmation_required",
                "message": "This session already has generated certificates or delivery activity. Confirm replacement to archive the active participant list without deleting its history.",
            },
        )
    import_id = str(uuid.uuid4())
    sent_by_email: dict[str, Participant] = {}
    for participant in sorted(
        batch.participants,
        key=lambda item: (item.sent_at or datetime.min).replace(tzinfo=None),
        reverse=True,
    ):
        canonical = participant.canonical_email or (participant.email.casefold() if participant.email else "")
        if participant.status == DeliveryStatus.SENT and canonical and canonical not in sent_by_email:
            sent_by_email[canonical] = participant

    # Archive previous active participants
    db.participants.update_many(
        {"batch_id": batch.id, "is_current_import": True},
        {"$set": {"is_current_import": False, "updated_at": datetime.now(timezone.utc)}},
    )

    new_participants: list[Participant] = []
    for row in rows:
        previous = sent_by_email.get(row.normalized_email) if row.is_valid else None
        p = Participant(
            batch_id=batch.id,
            row_number=row.row_number,
            name=row.name,
            email=row.email,
            normalized_email=f"__participant__:{uuid.uuid4()}",
            canonical_email=row.normalized_email or None,
            is_valid=row.is_valid,
            validation_error=row.error,
            is_current_import=True,
            import_id=import_id,
            certificate_code=generate_certificate_code(),
            is_excluded=bool(previous),
            status=DeliveryStatus.PENDING,
            previous_delivery_id=previous.id if previous else None,
            error_reason=(
                "Previously sent in an earlier import; excluded to prevent duplicate delivery"
                if previous
                else None
            ),
            idempotency_key=f"cert-{batch.id}-{uuid.uuid4()}",
            updated_at=datetime.now(timezone.utc),
        )
        new_participants.append(p)

    if new_participants:
        db.participants.insert_many([p.to_doc() for p in new_participants])

    now = datetime.now(timezone.utc)
    db.batches.update_one(
        {"_id": batch.id},
        {
            "$set": {
                "active_import_id": import_id,
                "generation_status": "IDLE",
                "generation_total": 0,
                "generation_succeeded": 0,
                "generation_failed": 0,
                "generation_current_name": None,
                "send_confirmed": False,
                "is_paused": False,
                "send_job_total": 0,
                "send_job_started_at": None,
                "send_job_finished_at": None,
                "updated_at": now,
            }
        },
    )

    updated_batch = batch_or_404(db, batch.id)
    result = serialize_batch(updated_batch)
    result["import_counts"] = {
        "total": len(rows),
        "valid": sum(row.is_valid for row in rows),
        "invalid": sum(not row.is_valid for row in rows),
        "duplicates": sum(bool(row.error and "Duplicate email" in row.error) for row in rows),
        "preserved": sum(1 for row in rows if row.is_valid and row.normalized_email in sent_by_email),
    }
    return result


@app.patch("/api/participants/{participant_id}", dependencies=[Depends(get_current_admin)])
def update_participant(participant_id: str, payload: ParticipantPatch, db: Any = Depends(get_db)):
    row_doc = db.participants.find_one({"_id": participant_id})
    if not row_doc:
        raise HTTPException(404, "Participant not found")
    batch = batch_or_404(db, row_doc["batch_id"])
    row = next((p for p in batch.participants if p.id == participant_id), None)
    if not row:
        raise HTTPException(404, "Participant not found")
    if not row.is_current_import:
        raise HTTPException(409, "Historical participant snapshots cannot be edited")
    if generation.is_running(row.batch_id) or batch.generation_status == "RUNNING":
        raise HTTPException(409, "Wait for certificate generation to finish before editing participants")
    content_changed = payload.name is not None or payload.email is not None
    if content_changed and row.status in {DeliveryStatus.SENT, DeliveryStatus.SENDING, DeliveryStatus.UNCERTAIN}:
        raise HTTPException(409, "Recipient details are locked after delivery starts; historical delivery snapshots cannot be changed")
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.email is not None:
        row.email = payload.email.strip()
    if payload.is_excluded is not None:
        row.is_excluded = payload.is_excluded
    revalidate_active_participants(batch)
    if content_changed and row.status != DeliveryStatus.SENT:
        row.certificate_path = row.preview_path = row.filename = row.legibility_warning = row.generation_error = None
        row.certificate_revision = None

    now = datetime.now(timezone.utc)
    for p in batch.participants:
        if p.is_current_import:
            db.participants.update_one(
                {"_id": p.id},
                {
                    "$set": {
                        "name": p.name,
                        "email": p.email,
                        "canonical_email": p.canonical_email,
                        "is_valid": p.is_valid,
                        "is_excluded": p.is_excluded,
                        "validation_error": p.validation_error,
                        "certificate_path": p.certificate_path,
                        "preview_path": p.preview_path,
                        "filename": p.filename,
                        "legibility_warning": p.legibility_warning,
                        "generation_error": p.generation_error,
                        "certificate_revision": p.certificate_revision,
                        "updated_at": now,
                    }
                },
            )
    db.batches.update_one({"_id": batch.id}, {"$set": {"updated_at": now}})
    return serialize_batch(batch_or_404(db, batch.id))


@app.post("/api/participants/{participant_id}/reconcile", dependencies=[Depends(get_current_admin)])
def reconcile_uncertain(participant_id: str, payload: ReconcileRequest, db: Any = Depends(get_db)):
    p_doc = db.participants.find_one({"_id": participant_id})
    if not p_doc:
        raise HTTPException(404, "Participant not found")
    participant = Participant.from_doc(p_doc)
    if participant.status != DeliveryStatus.UNCERTAIN:
        raise HTTPException(409, "Only an UNCERTAIN submission can be reconciled")
    expected = "CONFIRM SENT" if payload.action == "CONFIRM_SENT" else "CONFIRM NOT SENT"
    if payload.confirmation != expected:
        raise HTTPException(400, f"Confirmation must exactly match: {expected}")
    now = datetime.now(timezone.utc)

    attempt_doc = db.delivery_attempts.find_one(
        {"participant_id": participant.id, "$or": [{"outcome": "UNCERTAIN"}, {"outcome": None}]},
        sort=[("attempt_number", -1)],
    )
    if not attempt_doc:
        attempt_doc = db.delivery_attempts.find_one(
            {"participant_id": participant.id},
            sort=[("attempt_number", -1)],
        )
    if not attempt_doc:
        attempt = DeliveryAttempt(
            participant_id=participant.id,
            attempt_number=1,
            started_at=now,
            certificate_filename=participant.filename,
        )
        db.delivery_attempts.insert_one(attempt.to_doc())
        attempt_id = attempt.id
    else:
        attempt_id = attempt_doc["_id"]

    rec_doc = db.send_records.find_one(
        {"participant_id": participant.id, "status": "UNCERTAIN"},
        sort=[("reserved_at", -1)],
    )
    if not rec_doc:
        rec_doc = db.send_records.find_one(
            {"participant_id": participant.id},
            sort=[("reserved_at", -1)],
        )

    db.delivery_attempts.update_one(
        {"_id": attempt_id},
        {
            "$set": {
                "reconciliation_action": payload.action,
                "reconciliation_note": payload.note.strip() or None,
                "reconciled_at": now,
                "outcome": (
                    attempt_doc.get("outcome") or "UNCERTAIN"
                    if attempt_doc
                    else "UNCERTAIN"
                ),
            }
        },
    )

    batch_doc = db.batches.find_one({"_id": participant.batch_id})
    sender = settings.smtp_sender_email or (batch_doc.get("sender_email") if batch_doc else "localhost")
    if payload.action == "CONFIRM_SENT":
        message_id = message_id_for(participant.idempotency_key, sender or "localhost")
        db.participants.update_one(
            {"_id": participant.id},
            {
                "$set": {
                    "status": DeliveryStatus.SENT.value,
                    "smtp_message_id": message_id,
                    "sent_at": now,
                    "error_reason": "Manually reconciled after confirming the message in Gmail Sent",
                    "updated_at": now,
                }
            },
        )
        if rec_doc:
            db.send_records.update_one(
                {"_id": rec_doc["_id"]},
                {
                    "$set": {
                        "status": "SENT",
                        "smtp_message_id": message_id,
                        "error_reason": "Manually reconciled as accepted",
                    }
                },
            )
    else:
        db.participants.update_one(
            {"_id": participant.id},
            {
                "$set": {
                    "status": DeliveryStatus.FAILED.value,
                    "error_reason": "Manually reconciled as not sent; Retry Failed still requires explicit confirmation",
                    "updated_at": now,
                }
            },
        )
        if rec_doc:
            db.send_records.update_one(
                {"_id": rec_doc["_id"]},
                {
                    "$set": {
                        "status": "FAILED",
                        "counts_against_limit": True,
                        "error_reason": "Manually reconciled as not sent",
                    }
                },
            )

    return serialize_batch(batch_or_404(db, participant.batch_id))


@app.post("/api/batches/{batch_id}/participants/{participant_id}/revoke", dependencies=[Depends(get_current_admin)])
@app.post("/api/participants/{participant_id}/revoke", dependencies=[Depends(get_current_admin)])
def revoke_certificate(
    participant_id: str,
    payload: RevokeCertificateRequest | None = None,
    batch_id: str | None = None,
    db: Any = Depends(get_db),
):
    p_doc = db.participants.find_one({"_id": participant_id})
    if not p_doc:
        raise HTTPException(404, "Participant not found")
    if batch_id and p_doc.get("batch_id") != batch_id:
        raise HTTPException(404, "Participant not in specified batch")

    now = datetime.now(timezone.utc)
    reason = (
        payload.reason.strip()
        if payload and payload.reason and payload.reason.strip()
        else "Revoked by issuing authority"
    )
    db.participants.update_one(
        {"_id": participant_id},
        {
            "$set": {
                "is_revoked": True,
                "revoked_at": now,
                "revocation_reason": reason,
                "updated_at": now,
            }
        },
    )
    return serialize_batch(batch_or_404(db, p_doc["batch_id"]))


@app.post("/api/batches/{batch_id}/participants/{participant_id}/reactivate", dependencies=[Depends(get_current_admin)])
@app.post("/api/participants/{participant_id}/reactivate", dependencies=[Depends(get_current_admin)])
def reactivate_certificate(
    participant_id: str,
    batch_id: str | None = None,
    db: Any = Depends(get_db),
):
    p_doc = db.participants.find_one({"_id": participant_id})
    if not p_doc:
        raise HTTPException(404, "Participant not found")
    if batch_id and p_doc.get("batch_id") != batch_id:
        raise HTTPException(404, "Participant not in specified batch")

    now = datetime.now(timezone.utc)
    db.participants.update_one(
        {"_id": participant_id},
        {
            "$set": {
                "is_revoked": False,
                "revoked_at": None,
                "revocation_reason": None,
                "updated_at": now,
            }
        },
    )
    return serialize_batch(batch_or_404(db, p_doc["batch_id"]))


@app.post("/api/batches/{batch_id}/template", dependencies=[Depends(get_current_admin)])
async def upload_template(batch_id: str, file: UploadFile = File(...), db: Any = Depends(get_db)):
    batch = batch_or_404(db, batch_id)
    if generation.is_running(batch_id):
        raise HTTPException(409, "Wait for certificate generation to finish")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise HTTPException(400, "Template must be PNG or JPEG")
    data = await read_limited(file)
    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(400, "Invalid image content") from exc
    path = settings.upload_dir / f"{batch_id}-template{suffix}"
    path.write_bytes(data)
    batch.template_path = str(path.resolve())
    advance_certificate_revision(batch)
    now = datetime.now(timezone.utc)
    db.batches.update_one(
        {"_id": batch.id},
        {
            "$set": {
                "template_path": batch.template_path,
                "certificate_revision": batch.certificate_revision,
                "updated_at": now,
            }
        },
    )
    db.participants.update_many(
        {
            "batch_id": batch.id,
            "is_current_import": True,
            "status": {
                "$nin": [
                    DeliveryStatus.SENT.value,
                    DeliveryStatus.SENDING.value,
                    DeliveryStatus.UNCERTAIN.value,
                    "SENT",
                    "SENDING",
                    "UNCERTAIN",
                ]
            },
        },
        {
            "$set": {
                "certificate_path": None,
                "preview_path": None,
                "filename": None,
                "legibility_warning": None,
                "updated_at": now,
            }
        },
    )
    return serialize_batch(batch_or_404(db, batch.id))


@app.post("/api/batches/{batch_id}/font", dependencies=[Depends(get_current_admin)])
async def upload_font(batch_id: str, file: UploadFile = File(...), db: Any = Depends(get_db)):
    batch = batch_or_404(db, batch_id)
    if generation.is_running(batch_id):
        raise HTTPException(409, "Wait for certificate generation to finish")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".ttf", ".otf"}:
        raise HTTPException(400, "Font must be TTF or OTF")
    data = await read_limited(file)
    path = settings.upload_dir / f"{batch_id}-font{suffix}"
    path.write_bytes(data)
    try:
        ImageFont.truetype(str(path), 32)
    except OSError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(400, "Invalid or unsupported font file") from exc
    batch.font_path = str(path.resolve())
    advance_certificate_revision(batch)
    now = datetime.now(timezone.utc)
    db.batches.update_one(
        {"_id": batch.id},
        {
            "$set": {
                "font_path": batch.font_path,
                "certificate_revision": batch.certificate_revision,
                "updated_at": now,
            }
        },
    )
    db.participants.update_many(
        {
            "batch_id": batch.id,
            "is_current_import": True,
            "status": {
                "$nin": [
                    DeliveryStatus.SENT.value,
                    DeliveryStatus.SENDING.value,
                    DeliveryStatus.UNCERTAIN.value,
                    "SENT",
                    "SENDING",
                    "UNCERTAIN",
                ]
            },
        },
        {
            "$set": {
                "certificate_path": None,
                "preview_path": None,
                "filename": None,
                "legibility_warning": None,
                "updated_at": now,
            }
        },
    )
    return serialize_batch(batch_or_404(db, batch.id))


@app.post("/api/batches/{batch_id}/font/default", dependencies=[Depends(get_current_admin)])
def use_default_font(batch_id: str, db: Any = Depends(get_db)):
    batch = batch_or_404(db, batch_id)
    if generation.is_running(batch_id):
        raise HTTPException(409, "Wait for certificate generation to finish")
    batch.font_path = None
    advance_certificate_revision(batch)
    now = datetime.now(timezone.utc)
    db.batches.update_one(
        {"_id": batch.id},
        {
            "$set": {
                "font_path": None,
                "certificate_revision": batch.certificate_revision,
                "updated_at": now,
            }
        },
    )
    db.participants.update_many(
        {
            "batch_id": batch.id,
            "is_current_import": True,
            "status": {
                "$nin": [
                    DeliveryStatus.SENT.value,
                    DeliveryStatus.SENDING.value,
                    DeliveryStatus.UNCERTAIN.value,
                    "SENT",
                    "SENDING",
                    "UNCERTAIN",
                ]
            },
        },
        {
            "$set": {
                "certificate_path": None,
                "preview_path": None,
                "filename": None,
                "legibility_warning": None,
                "updated_at": now,
            }
        },
    )
    return serialize_batch(batch_or_404(db, batch.id))


@app.get("/api/batches/{batch_id}/template-file", dependencies=[Depends(get_current_admin)])
def template_file(batch_id: str, db: Any = Depends(get_db)):
    batch = batch_or_404(db, batch_id)
    if not batch.template_path:
        raise HTTPException(404, "Template not uploaded")
    suffix = Path(batch.template_path).suffix.lower()
    return FileResponse(batch.template_path, media_type="image/png" if suffix == ".png" else "image/jpeg")


@app.post("/api/batches/{batch_id}/render-preview", dependencies=[Depends(get_current_admin)])
def render_live_preview(batch_id: str, payload: PreviewRequest, db: Any = Depends(get_db)):
    batch = batch_or_404(db, batch_id)
    if not batch.template_path:
        raise HTTPException(409, "Upload the certificate template first")
    participant_doc = db.participants.find_one({"_id": payload.participant_id})
    if (
        not participant_doc
        or participant_doc.get("batch_id") != batch.id
        or not participant_doc.get("is_current_import")
        or not participant_doc.get("is_valid")
        or participant_doc.get("is_excluded")
    ):
        raise HTTPException(404, "Preview participant is not available")
    participant = Participant.from_doc(participant_doc)
    if payload.x + payload.w > 1 or payload.y + payload.h > 1:
        raise HTTPException(422, "Name region must stay inside the image")
    png, actual_size, warning = render_preview_png(
        Path(batch.template_path),
        resolve_font_path(batch.font_path),
        participant.name,
        payload.model_dump(exclude={"participant_id"}),
        certificate_code=participant.certificate_code,
    )
    return Response(
        png,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store",
            "X-Actual-Font-Size": str(actual_size),
            "X-Legibility-Warning": "1" if warning else "0",
        },
    )


@app.put("/api/batches/{batch_id}/region", dependencies=[Depends(get_current_admin)])
def update_region(batch_id: str, payload: RegionUpdate, db: Any = Depends(get_db)):
    if payload.x + payload.w > 1 or payload.y + payload.h > 1:
        raise HTTPException(422, "Name region must stay inside the image")
    batch = batch_or_404(db, batch_id)
    if generation.is_running(batch_id):
        raise HTTPException(409, "Wait for certificate generation to finish")
    update_fields = {}
    for key, value in payload.model_dump().items():
        field_name = f"region_{key}" if key in {"x", "y", "w", "h"} else key
        update_fields[field_name] = value
    new_rev = str(uuid.uuid4())
    update_fields["certificate_revision"] = new_rev
    now = datetime.now(timezone.utc)
    update_fields["updated_at"] = now
    db.batches.update_one({"_id": batch.id}, {"$set": update_fields})
    db.participants.update_many(
        {
            "batch_id": batch.id,
            "is_current_import": True,
            "status": {
                "$nin": [
                    DeliveryStatus.SENT.value,
                    DeliveryStatus.SENDING.value,
                    DeliveryStatus.UNCERTAIN.value,
                    "SENT",
                    "SENDING",
                    "UNCERTAIN",
                ]
            },
        },
        {
            "$set": {
                "certificate_path": None,
                "preview_path": None,
                "filename": None,
                "legibility_warning": None,
                "updated_at": now,
            }
        },
    )
    return serialize_batch(batch_or_404(db, batch.id))


@app.post("/api/batches/{batch_id}/generate", dependencies=[Depends(get_current_admin)])
def generate(batch_id: str, db: Any = Depends(get_db)):
    batch = batch_or_404(db, batch_id)
    if not batch.template_path:
        raise HTTPException(409, "Upload a certificate template first")
    eligible = [
        row for row in batch.participants
        if row.is_current_import and row.is_valid and not row.is_excluded
    ]
    if not eligible:
        raise HTTPException(409, "No valid included participants are eligible for generation")
    if generation.is_running(batch_id) or batch.generation_status == "RUNNING":
        raise HTTPException(409, "Certificate generation is already running for this batch")
    if not generation.start(batch_id):
        raise HTTPException(409, "Certificate generation is already running for this batch")
    return {"started": True, "total": len(eligible)}


@app.post("/api/batches/{batch_id}/participants/{participant_id}/generate", dependencies=[Depends(get_current_admin)])
def generate_participant(batch_id: str, participant_id: str, db: Any = Depends(get_db)):
    p_doc = db.participants.find_one({"_id": participant_id})
    if not p_doc or p_doc.get("batch_id") != batch_id or not p_doc.get("is_current_import"):
        raise HTTPException(404, "Participant not found")
    participant = Participant.from_doc(p_doc)
    batch = batch_or_404(db, batch_id)
    if not participant.is_valid or participant.is_excluded:
        raise HTTPException(409, "Only valid included participants can be regenerated")
    if not batch.template_path:
        raise HTTPException(409, "Upload a certificate template first")
    if generation.is_running(batch.id) or batch.generation_status == "RUNNING":
        raise HTTPException(409, "Certificate generation is already running for this session")
    if not generation.start(batch.id, participant.id):
        raise HTTPException(409, "Certificate generation is already running for this session")
    return {"started": True, "total": 1, "participant_id": participant.id}


@app.get("/api/participants/{participant_id}/preview", dependencies=[Depends(get_current_admin)])
def preview(participant_id: str, db: Any = Depends(get_db)):
    row = db.participants.find_one({"_id": participant_id})
    if not row or not row.get("preview_path"):
        raise HTTPException(404, "Preview not generated")
    return FileResponse(row["preview_path"], media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/participants/{participant_id}/certificate", dependencies=[Depends(get_current_admin)])
def certificate(participant_id: str, db: Any = Depends(get_db)):
    row = db.participants.find_one({"_id": participant_id})
    if not row or not row.get("certificate_path"):
        raise HTTPException(404, "Certificate not generated")
    return FileResponse(row["certificate_path"], media_type="application/pdf", filename=row.get("filename"))


@app.get("/api/batches/{batch_id}/zip", dependencies=[Depends(get_current_admin)])
def download_zip(batch_id: str, db: Any = Depends(get_db)):
    batch = batch_or_404(db, batch_id)
    files = [
        (Path(p.certificate_path), p.filename or "certificate.pdf")
        for p in batch.participants
        if p.is_current_import
        and p.certificate_path
        and not p.is_excluded
        and p.certificate_revision == batch.certificate_revision
        and is_render_current(p.certificate_path)
    ]
    if not files:
        raise HTTPException(409, "Generate certificates first")
    path = make_zip(files, settings.generated_dir / f"{batch.id}-certificates.zip")
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"{safe_filename(batch.name)}-certificates.zip",
    )


@app.put("/api/batches/{batch_id}/email", dependencies=[Depends(get_current_admin)])
def configure_email(batch_id: str, payload: EmailConfig, db: Any = Depends(get_db)):
    batch = batch_or_404(db, batch_id)
    if str(payload.sender_email).casefold() not in allowed_senders():
        raise HTTPException(400, "Sender must match SMTP_SENDER_EMAIL or an address in SMTP_ALLOWED_ALIASES")
    now = datetime.now(timezone.utc)
    db.batches.update_one(
        {"_id": batch.id},
        {
            "$set": {
                "sender_email": str(payload.sender_email),
                "email_subject": payload.subject,
                "email_body": payload.body,
                "updated_at": now,
            }
        },
    )
    return serialize_batch(batch_or_404(db, batch.id))


@app.get("/api/smtp/status")
def smtp_status():
    return {
        "configured": smtp_configured(),
        "sender_email": settings.smtp_sender_email if smtp_configured() else None,
        "aliases": settings.smtp_aliases if smtp_configured() else [],
        "host": settings.smtp_host,
        "port": settings.smtp_port,
        "provider": "Gmail" if "gmail" in settings.smtp_host.casefold() else settings.smtp_host,
        "application_cap": settings.max_emails_per_day,
    }


@app.get("/api/sending-allowance", dependencies=[Depends(get_current_admin)])
def sending_allowance():
    return delivery.allowance()


@app.post("/api/batches/{batch_id}/send", dependencies=[Depends(get_current_admin)])
def start_send(batch_id: str, payload: StartSendRequest, db: Any = Depends(get_db)):
    batch = batch_or_404(db, batch_id)
    if delivery.is_running(batch_id):
        raise HTTPException(409, "A sending worker is already active for this batch")
    pending_eligible = [
        p for p in batch.participants
        if p.is_current_import and p.is_valid and not p.is_excluded and p.status == DeliveryStatus.PENDING
    ]
    ready = sum(
        1 for p in pending_eligible
        if p.certificate_revision == batch.certificate_revision
        and is_render_current(p.certificate_path)
    )
    expected = f"SEND {ready}"
    if payload.confirmation != expected:
        raise HTTPException(400, f"Confirmation must exactly match: {expected}")
    if ready == 0:
        raise HTTPException(409, "No pending participants have a current generated certificate")
    if ready != len(pending_eligible):
        raise HTTPException(
            409,
            f"Generate current PDFs for all {len(pending_eligible)} pending eligible participants before sending",
        )
    if not batch.sender_email or not batch.email_subject.strip() or not batch.email_body.strip():
        raise HTTPException(409, "Configure sender, subject, and email body first")
    if not smtp_configured():
        raise HTTPException(503, "SMTP App Password is not configured")
    if batch.sender_email.casefold() not in allowed_senders():
        raise HTTPException(400, "Sender is not the configured Gmail account or an allowed alias")
    remaining = delivery.allowance()["remaining"]
    if remaining is not None and remaining <= 0:
        raise HTTPException(429, "Rolling 24-hour application sending limit reached")
    now = datetime.now(timezone.utc)
    db.batches.update_one(
        {"_id": batch.id},
        {
            "$set": {
                "send_confirmed": True,
                "is_paused": False,
                "send_job_total": ready,
                "send_job_started_at": now,
                "send_job_finished_at": None,
                "updated_at": now,
            }
        },
    )
    if not delivery.start(batch.id):
        raise HTTPException(409, "A sending worker is already active for this batch")
    return {"started": True}


@app.post("/api/batches/{batch_id}/pause", dependencies=[Depends(get_current_admin)])
def pause(batch_id: str, db: Any = Depends(get_db)):
    batch = batch_or_404(db, batch_id)
    db.batches.update_one(
        {"_id": batch_id},
        {"$set": {"is_paused": True, "updated_at": datetime.now(timezone.utc)}},
    )
    return {"paused": True}


@app.post("/api/batches/{batch_id}/resume", dependencies=[Depends(get_current_admin)])
def resume(batch_id: str, db: Any = Depends(get_db)):
    batch = batch_or_404(db, batch_id)
    db.batches.update_one(
        {"_id": batch_id},
        {"$set": {"is_paused": False, "updated_at": datetime.now(timezone.utc)}},
    )
    delivery.start(batch.id)
    return {"resumed": True}


@app.post("/api/batches/{batch_id}/retry-failed", dependencies=[Depends(get_current_admin)])
def retry_failed(batch_id: str, db: Any = Depends(get_db)):
    batch = batch_or_404(db, batch_id)
    now = datetime.now(timezone.utc)
    res = db.participants.update_many(
        {
            "batch_id": batch_id,
            "is_current_import": True,
            "status": {
                "$in": [
                    DeliveryStatus.FAILED.value,
                    str(DeliveryStatus.FAILED),
                    "FAILED",
                ]
            },
        },
        {"$set": {"status": DeliveryStatus.PENDING.value, "error_reason": None, "updated_at": now}},
    )
    return {"reset": res.modified_count}


@app.get("/api/batches/{batch_id}/events", dependencies=[Depends(get_current_admin)])
async def events(batch_id: str, request: Request):
    async def stream():
        previous = None
        while not await request.is_disconnected():
            with SessionLocal() as db:
                batch = get_batch_model(db, batch_id)
                if not batch:
                    yield "event: error\ndata: Batch not found\n\n"
                    return
                payload = json.dumps(serialize_batch(batch))
            if payload != previous:
                yield f"data: {payload}\n\n"
                previous = payload
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/batches/{batch_id}/report", dependencies=[Depends(get_current_admin)])
def report(batch_id: str, db: Any = Depends(get_db)):
    batch = batch_or_404(db, batch_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Certificate ID",
        "Recipient",
        "Name",
        "Included",
        "Status",
        "Timestamp",
        "SMTP Message ID",
        "Delivery Reference",
        "Previous Delivery ID",
        "Last Attempt",
        "Reconciliation",
        "Error Reason",
    ])
    for p in sorted((row for row in batch.participants if row.is_current_import), key=lambda item: item.row_number):
        timestamp = p.sent_at or (p.updated_at if p.status != DeliveryStatus.PENDING else None)
        attempt = max(p.attempts, key=lambda item: item.attempt_number, default=None)
        writer.writerow([
            csv_safe(p.certificate_code),
            csv_safe(p.email),
            csv_safe(p.name),
            "No" if p.is_excluded else "Yes",
            p.status.value,
            timestamp.isoformat() if timestamp else "",
            csv_safe(p.smtp_message_id),
            csv_safe(p.idempotency_key),
            csv_safe(p.previous_delivery_id),
            csv_safe(attempt.outcome if attempt else None),
            csv_safe(attempt.reconciliation_action if attempt else None),
            csv_safe(p.error_reason),
        ])
    data = buffer.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        iter([data]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename(batch.name)}-delivery-report.csv"'},
    )
