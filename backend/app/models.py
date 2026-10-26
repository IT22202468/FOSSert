from dataclasses import dataclass, field
from datetime import datetime, timezone
import enum
from typing import Any
import uuid


DEFAULT_EMAIL_SUBJECT = "Your Certificate of Participation"
DEFAULT_EMAIL_BODY = """Hi {name},

Thank you for participating in our event!

We appreciate your time, enthusiasm, and involvement. Please find your personalized certificate of participation attached to this email.

We hope you enjoyed the experience and look forward to seeing you at our future events.

Best regards,
Event Organizing Team"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeliveryStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"


class DocumentModel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)


class Batch(DocumentModel):
    def __init__(
        self,
        id: str | None = None,
        name: str = "Certificate batch",
        name_normalized: str | None = None,
        workshop_name: str = "Workshop",
        template_path: str | None = None,
        font_path: str | None = None,
        certificate_revision: str | None = None,
        region_x: float = 0.2,
        region_y: float = 0.45,
        region_w: float = 0.6,
        region_h: float = 0.12,
        font_size: int = 110,
        min_font_size: int = 38,
        auto_fit: bool = True,
        vertical_offset: int = 0,
        sender_email: str | None = None,
        email_subject: str = DEFAULT_EMAIL_SUBJECT,
        email_body: str = DEFAULT_EMAIL_BODY,
        is_paused: bool = False,
        send_confirmed: bool = False,
        send_job_total: int = 0,
        send_job_started_at: datetime | None = None,
        send_job_finished_at: datetime | None = None,
        active_import_id: str | None = None,
        generation_job_id: str | None = None,
        generation_status: str = "IDLE",
        generation_total: int = 0,
        generation_succeeded: int = 0,
        generation_failed: int = 0,
        generation_current_name: str | None = None,
        generation_started_at: datetime | None = None,
        generation_finished_at: datetime | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        participants: list["Participant"] | None = None,
        **extra,
    ):
        self.id = id or str(uuid.uuid4())
        self.name = name
        if name_normalized:
            self.name_normalized = name_normalized
        else:
            self.name_normalized = f"{name.lower().strip()}-{self.id}" if name == "Certificate batch" else name.lower().strip()
        self.workshop_name = workshop_name
        self.template_path = template_path
        self.font_path = font_path
        self.certificate_revision = certificate_revision or str(uuid.uuid4())
        self.region_x = float(region_x)
        self.region_y = float(region_y)
        self.region_w = float(region_w)
        self.region_h = float(region_h)
        self.font_size = int(font_size)
        self.min_font_size = int(min_font_size)
        self.auto_fit = bool(auto_fit)
        self.vertical_offset = int(vertical_offset)
        self.sender_email = sender_email
        self.email_subject = email_subject
        self.email_body = email_body
        self.is_paused = bool(is_paused)
        self.send_confirmed = bool(send_confirmed)
        self.send_job_total = int(send_job_total)
        self.send_job_started_at = send_job_started_at
        self.send_job_finished_at = send_job_finished_at
        self.active_import_id = active_import_id
        self.generation_job_id = generation_job_id
        self.generation_status = generation_status
        self.generation_total = int(generation_total)
        self.generation_succeeded = int(generation_succeeded)
        self.generation_failed = int(generation_failed)
        self.generation_current_name = generation_current_name
        self.generation_started_at = generation_started_at
        self.generation_finished_at = generation_finished_at
        self.created_at = created_at or utcnow()
        self.updated_at = updated_at or utcnow()
        self.participants = participants if participants is not None else []
        for k, v in extra.items():
            setattr(self, k, v)

    @property
    def region(self) -> dict:
        return {
            "x": self.region_x,
            "y": self.region_y,
            "w": self.region_w,
            "h": self.region_h,
            "font_size": self.font_size,
            "min_font_size": self.min_font_size,
            "auto_fit": self.auto_fit,
            "vertical_offset": self.vertical_offset,
        }

    def to_doc(self) -> dict:
        return {
            "_id": self.id,
            "name": self.name,
            "name_normalized": self.name_normalized,
            "workshop_name": self.workshop_name,
            "template_path": self.template_path,
            "font_path": self.font_path,
            "certificate_revision": self.certificate_revision,
            "region_x": self.region_x,
            "region_y": self.region_y,
            "region_w": self.region_w,
            "region_h": self.region_h,
            "font_size": self.font_size,
            "min_font_size": self.min_font_size,
            "auto_fit": self.auto_fit,
            "vertical_offset": self.vertical_offset,
            "sender_email": self.sender_email,
            "email_subject": self.email_subject,
            "email_body": self.email_body,
            "is_paused": self.is_paused,
            "send_confirmed": self.send_confirmed,
            "send_job_total": self.send_job_total,
            "send_job_started_at": self.send_job_started_at,
            "send_job_finished_at": self.send_job_finished_at,
            "active_import_id": self.active_import_id,
            "generation_job_id": self.generation_job_id,
            "generation_status": self.generation_status,
            "generation_total": self.generation_total,
            "generation_succeeded": self.generation_succeeded,
            "generation_failed": self.generation_failed,
            "generation_current_name": self.generation_current_name,
            "generation_started_at": self.generation_started_at,
            "generation_finished_at": self.generation_finished_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_doc(cls, doc: dict | None) -> "Batch | None":
        if not doc:
            return None
        d = dict(doc)
        doc_id = d.pop("_id", None) or d.pop("id", None)
        return cls(id=str(doc_id), **d)


class Participant(DocumentModel):
    def __init__(
        self,
        id: str | None = None,
        batch_id: str = "",
        row_number: int = 1,
        name: str = "",
        email: str = "",
        normalized_email: str = "",
        canonical_email: str | None = None,
        is_valid: bool = True,
        is_excluded: bool = False,
        validation_error: str | None = None,
        is_current_import: bool = True,
        import_id: str | None = None,
        previous_delivery_id: str | None = None,
        certificate_path: str | None = None,
        preview_path: str | None = None,
        filename: str | None = None,
        legibility_warning: str | None = None,
        generation_error: str | None = None,
        certificate_revision: str | None = None,
        status: DeliveryStatus | str = DeliveryStatus.PENDING,
        smtp_message_id: str | None = None,
        sent_at: datetime | None = None,
        error_reason: str | None = None,
        is_revoked: bool = False,
        revoked_at: datetime | None = None,
        revocation_reason: str | None = None,
        idempotency_key: str | None = None,
        certificate_code: str | None = None,
        updated_at: datetime | None = None,
        attempts: list["DeliveryAttempt"] | None = None,
        batch: Batch | None = None,
        **extra,
    ):
        self.id = id or str(uuid.uuid4())
        self.batch_id = str(batch_id)
        self.row_number = int(row_number)
        self.name = name
        self.email = email
        self.normalized_email = normalized_email or email.lower().strip()
        self.canonical_email = canonical_email or self.normalized_email
        self.is_valid = bool(is_valid)
        self.is_excluded = bool(is_excluded)
        self.validation_error = validation_error
        self.is_current_import = bool(is_current_import)
        self.import_id = import_id
        self.previous_delivery_id = previous_delivery_id
        self.certificate_path = certificate_path
        self.preview_path = preview_path
        self.filename = filename
        self.legibility_warning = legibility_warning
        self.generation_error = generation_error
        self.certificate_revision = certificate_revision
        self.status = DeliveryStatus(status) if isinstance(status, str) else status
        self.smtp_message_id = smtp_message_id
        self.sent_at = sent_at
        self.error_reason = error_reason
        self.is_revoked = bool(is_revoked)
        self.revoked_at = revoked_at
        self.revocation_reason = revocation_reason
        self.idempotency_key = idempotency_key or str(uuid.uuid4())
        self.certificate_code = certificate_code
        self.updated_at = updated_at or utcnow()
        self.attempts = attempts if attempts is not None else []
        self.batch = batch
        for k, v in extra.items():
            setattr(self, k, v)

    def to_doc(self) -> dict:
        return {
            "_id": self.id,
            "batch_id": self.batch_id,
            "row_number": self.row_number,
            "name": self.name,
            "email": self.email,
            "normalized_email": self.normalized_email,
            "canonical_email": self.canonical_email,
            "is_valid": self.is_valid,
            "is_excluded": self.is_excluded,
            "validation_error": self.validation_error,
            "is_current_import": self.is_current_import,
            "import_id": self.import_id,
            "previous_delivery_id": self.previous_delivery_id,
            "certificate_path": self.certificate_path,
            "preview_path": self.preview_path,
            "filename": self.filename,
            "legibility_warning": self.legibility_warning,
            "generation_error": self.generation_error,
            "certificate_revision": self.certificate_revision,
            "status": self.status.value if isinstance(self.status, DeliveryStatus) else str(self.status),
            "smtp_message_id": self.smtp_message_id,
            "sent_at": self.sent_at,
            "error_reason": self.error_reason,
            "is_revoked": self.is_revoked,
            "revoked_at": self.revoked_at,
            "revocation_reason": self.revocation_reason,
            "idempotency_key": self.idempotency_key,
            "certificate_code": self.certificate_code,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_doc(cls, doc: dict | None) -> "Participant | None":
        if not doc:
            return None
        d = dict(doc)
        doc_id = d.pop("_id", None) or d.pop("id", None)
        return cls(id=str(doc_id), **d)


class DeliveryAttempt(DocumentModel):
    def __init__(
        self,
        id: str | int | None = None,
        participant_id: str = "",
        attempt_number: int = 1,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        outcome: str | None = None,
        smtp_message_id: str | None = None,
        certificate_path: str | None = None,
        certificate_filename: str | None = None,
        error_code: str | None = None,
        error_reason: str | None = None,
        reconciliation_action: str | None = None,
        reconciliation_note: str | None = None,
        reconciled_at: datetime | None = None,
        participant: Participant | None = None,
        **extra,
    ):
        self.id = id if id is not None else str(uuid.uuid4())
        self.participant_id = str(participant_id)
        self.attempt_number = int(attempt_number)
        self.started_at = started_at or utcnow()
        self.finished_at = finished_at
        self.outcome = outcome
        self.smtp_message_id = smtp_message_id
        self.certificate_path = certificate_path
        self.certificate_filename = certificate_filename
        self.error_code = error_code
        self.error_reason = error_reason
        self.reconciliation_action = reconciliation_action
        self.reconciliation_note = reconciliation_note
        self.reconciled_at = reconciled_at
        self.participant = participant
        for k, v in extra.items():
            setattr(self, k, v)

    def to_doc(self) -> dict:
        return {
            "_id": self.id,
            "participant_id": self.participant_id,
            "attempt_number": self.attempt_number,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "outcome": self.outcome,
            "smtp_message_id": self.smtp_message_id,
            "certificate_path": self.certificate_path,
            "certificate_filename": self.certificate_filename,
            "error_code": self.error_code,
            "error_reason": self.error_reason,
            "reconciliation_action": self.reconciliation_action,
            "reconciliation_note": self.reconciliation_note,
            "reconciled_at": self.reconciled_at,
        }

    @classmethod
    def from_doc(cls, doc: dict | None) -> "DeliveryAttempt | None":
        if not doc:
            return None
        d = dict(doc)
        doc_id = d.pop("_id", None) or d.pop("id", None)
        return cls(id=doc_id, **d)


class SendRecord(DocumentModel):
    def __init__(
        self,
        id: str | None = None,
        batch_id: str | None = None,
        participant_id: str | None = None,
        kind: str = "BULK",
        status: str = "RESERVED",
        counts_against_limit: bool = True,
        reserved_at: datetime | None = None,
        finished_at: datetime | None = None,
        smtp_message_id: str | None = None,
        error_reason: str | None = None,
        **extra,
    ):
        self.id = id or str(uuid.uuid4())
        self.batch_id = batch_id
        self.participant_id = participant_id
        self.kind = kind
        self.status = status
        self.counts_against_limit = bool(counts_against_limit)
        self.reserved_at = reserved_at or utcnow()
        self.finished_at = finished_at
        self.smtp_message_id = smtp_message_id
        self.error_reason = error_reason
        for k, v in extra.items():
            setattr(self, k, v)

    def to_doc(self) -> dict:
        return {
            "_id": self.id,
            "batch_id": self.batch_id,
            "participant_id": self.participant_id,
            "kind": self.kind,
            "status": self.status,
            "counts_against_limit": self.counts_against_limit,
            "reserved_at": self.reserved_at,
            "finished_at": self.finished_at,
            "smtp_message_id": self.smtp_message_id,
            "error_reason": self.error_reason,
        }

    @classmethod
    def from_doc(cls, doc: dict | None) -> "SendRecord | None":
        if not doc:
            return None
        d = dict(doc)
        doc_id = d.pop("_id", None) or d.pop("id", None)
        return cls(id=str(doc_id), **d)


class AdminUser(DocumentModel):
    def __init__(
        self,
        id: str | None = None,
        username: str = "",
        password_hash: str = "",
        salt: str = "",
        created_at: datetime | None = None,
        **extra,
    ):
        self.id = id or str(uuid.uuid4())
        self.username = username
        self.password_hash = password_hash
        self.salt = salt
        self.created_at = created_at or utcnow()
        for k, v in extra.items():
            setattr(self, k, v)

    def to_doc(self) -> dict:
        return {
            "_id": self.id,
            "username": self.username,
            "password_hash": self.password_hash,
            "salt": self.salt,
            "created_at": self.created_at,
        }

    @classmethod
    def from_doc(cls, doc: dict | None) -> "AdminUser | None":
        if not doc:
            return None
        d = dict(doc)
        doc_id = d.pop("_id", None) or d.pop("id", None)
        return cls(id=str(doc_id), **d)


class AdminSession(DocumentModel):
    def __init__(
        self,
        token: str = "",
        user_id: str = "",
        created_at: datetime | None = None,
        expires_at: datetime | None = None,
        user: AdminUser | None = None,
        **extra,
    ):
        self.token = token
        self.user_id = user_id
        self.created_at = created_at or utcnow()
        self.expires_at = expires_at or utcnow()
        self.user = user
        for k, v in extra.items():
            setattr(self, k, v)

    def to_doc(self) -> dict:
        return {
            "_id": self.token,
            "token": self.token,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_doc(cls, doc: dict | None) -> "AdminSession | None":
        if not doc:
            return None
        d = dict(doc)
        token = d.pop("_id", None)
        token = d.pop("token", token)
        return cls(token=str(token), **d)
