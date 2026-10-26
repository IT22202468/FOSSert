from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Generator
import uuid

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from .config import get_settings


logger = logging.getLogger("certificate.database")

_client: MongoClient | None = None
_test_db: Database | None = None


def clean_session_name(value: str | None) -> str:
    """Normalize display whitespace and enforce the public session-name contract."""
    cleaned = " ".join((value or "").strip().split())
    if not cleaned:
        raise ValueError("Session name is required")
    if len(cleaned) > 100:
        raise ValueError("Session name must be 100 characters or fewer")
    return cleaned


def normalized_session_name(value: str) -> str:
    return clean_session_name(value).casefold()


def relocated_path(raw_path: str | None, base_dir: Path) -> str | None:
    if not raw_path:
        return None
    p = Path(raw_path)
    if p.exists():
        return str(p.resolve())
    candidate = base_dir / p.name
    if candidate.exists():
        return str(candidate.resolve())
    return raw_path


def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = MongoClient(settings.mongodb_uri, timeoutMS=5000, serverSelectionTimeoutMS=5000)
    return _client


def set_test_db(db: Database | None) -> None:
    global _test_db
    _test_db = db


def get_db_instance() -> Database:
    if _test_db is not None:
        return _test_db
    settings = get_settings()
    client = get_mongo_client()
    return client[settings.mongodb_db_name]


class DatabaseContext:
    """Context manager replacing SessionLocal() for thread workers and tests."""
    def __init__(self):
        self._db = get_db_instance()
        self._identity_map: dict[tuple[type, str], Any] = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def __getattr__(self, name: str) -> Any:
        return getattr(self._db, name)

    def __getitem__(self, name: str) -> Any:
        return self._db[name]

    def _save_obj(self, obj: Any) -> None:
        from .models import (
            Batch, Participant, DeliveryAttempt, SendRecord, AdminUser, AdminSession
        )
        if isinstance(obj, Batch):
            self._db.batches.replace_one({"_id": obj.id}, obj.to_doc(), upsert=True)
        elif isinstance(obj, Participant):
            self._db.participants.replace_one({"_id": obj.id}, obj.to_doc(), upsert=True)
        elif isinstance(obj, DeliveryAttempt):
            self._db.delivery_attempts.replace_one({"_id": obj.id}, obj.to_doc(), upsert=True)
        elif isinstance(obj, SendRecord):
            self._db.send_records.replace_one({"_id": obj.id}, obj.to_doc(), upsert=True)
        elif isinstance(obj, AdminUser):
            self._db.admin_users.replace_one({"_id": obj.id}, obj.to_doc(), upsert=True)
        elif isinstance(obj, AdminSession):
            self._db.admin_sessions.replace_one({"_id": obj.id}, obj.to_doc(), upsert=True)

    def add(self, obj: Any) -> None:
        self._save_obj(obj)
        obj_id = getattr(obj, "id", None) or getattr(obj, "token", None)
        if obj_id:
            self._identity_map[(type(obj), obj_id)] = obj

    def commit(self) -> None:
        for obj in list(self._identity_map.values()):
            self._save_obj(obj)

    def flush(self) -> None:
        self.commit()

    def rollback(self) -> None:
        pass

    def refresh(self, obj: Any) -> None:
        from .models import Batch, Participant
        if isinstance(obj, Batch):
            doc = self._db.batches.find_one({"_id": obj.id})
            if doc:
                b = Batch.from_doc(doc)
                obj.__dict__.update(b.__dict__)
        elif isinstance(obj, Participant):
            doc = self._db.participants.find_one({"_id": obj.id})
            if doc:
                p = Participant.from_doc(doc)
                obj.__dict__.update(p.__dict__)

    def get(self, model_cls: Any, obj_id: str) -> Any:
        from .models import (
            Batch, Participant, DeliveryAttempt, SendRecord, AdminUser, AdminSession
        )
        if issubclass(model_cls, Batch):
            doc = self._db.batches.find_one({"_id": obj_id})
            if doc:
                obj = Batch.from_doc(doc)
                p_docs = list(self._db.participants.find({"batch_id": obj_id}).sort("row_number", 1))
                p_ids = [p["_id"] for p in p_docs]
                att_docs = list(self._db.delivery_attempts.find({"participant_id": {"$in": p_ids}}).sort("attempt_number", 1))
                att_by_p: dict[str, list[DeliveryAttempt]] = {}
                for a in att_docs:
                    att_by_p.setdefault(a["participant_id"], []).append(DeliveryAttempt.from_doc(a))
                participants = []
                for p in p_docs:
                    part = Participant.from_doc(p)
                    part.attempts = att_by_p.get(part.id, [])
                    part.batch = obj
                    participants.append(part)
                obj.participants = participants
            else:
                obj = None
        elif issubclass(model_cls, Participant):
            doc = self._db.participants.find_one({"_id": obj_id})
            if doc:
                obj = Participant.from_doc(doc)
                att_docs = list(self._db.delivery_attempts.find({"participant_id": obj_id}).sort("attempt_number", 1))
                obj.attempts = [DeliveryAttempt.from_doc(a) for a in att_docs]
                batch_doc = self._db.batches.find_one({"_id": obj.batch_id})
                obj.batch = Batch.from_doc(batch_doc) if batch_doc else None
            else:
                obj = None
        elif issubclass(model_cls, DeliveryAttempt):
            doc = self._db.delivery_attempts.find_one({"_id": obj_id})
            obj = DeliveryAttempt.from_doc(doc) if doc else None
        elif issubclass(model_cls, SendRecord):
            doc = self._db.send_records.find_one({"_id": obj_id})
            obj = SendRecord.from_doc(doc) if doc else None
        elif issubclass(model_cls, AdminUser):
            doc = self._db.admin_users.find_one({"_id": obj_id})
            obj = AdminUser.from_doc(doc) if doc else None
        elif issubclass(model_cls, AdminSession):
            doc = self._db.admin_sessions.find_one({"_id": obj_id})
            obj = AdminSession.from_doc(doc) if doc else None
        else:
            obj = None
        if obj:
            self._identity_map[(model_cls, obj_id)] = obj
        return obj

    def query(self, model_cls: Any) -> Any:
        class _Query:
            def __init__(query_self, db, cls):
                query_self._db = db
                query_self._cls = cls

            def count(query_self) -> int:
                from .models import (
                    Batch, Participant, DeliveryAttempt, SendRecord, AdminUser, AdminSession
                )
                if issubclass(query_self._cls, SendRecord):
                    return query_self._db.send_records.count_documents({})
                elif issubclass(query_self._cls, Participant):
                    return query_self._db.participants.count_documents({})
                elif issubclass(query_self._cls, Batch):
                    return query_self._db.batches.count_documents({})
                elif issubclass(query_self._cls, DeliveryAttempt):
                    return query_self._db.delivery_attempts.count_documents({})
                elif issubclass(query_self._cls, AdminUser):
                    return query_self._db.admin_users.count_documents({})
                elif issubclass(query_self._cls, AdminSession):
                    return query_self._db.admin_sessions.count_documents({})
                return 0

        return _Query(self._db, model_cls)

    def delete(self, obj: Any) -> None:
        from .models import (
            Batch, Participant, DeliveryAttempt, SendRecord, AdminUser, AdminSession
        )
        obj_id = getattr(obj, "id", None) or getattr(obj, "token", None) or str(obj)
        if isinstance(obj, Batch):
            self._db.batches.delete_one({"_id": obj_id})
        elif isinstance(obj, Participant):
            self._db.participants.delete_one({"_id": obj_id})
        elif isinstance(obj, DeliveryAttempt):
            self._db.delivery_attempts.delete_one({"_id": obj_id})
        elif isinstance(obj, SendRecord):
            self._db.send_records.delete_one({"_id": obj_id})
        elif isinstance(obj, AdminUser):
            self._db.admin_users.delete_one({"_id": obj_id})
        elif isinstance(obj, AdminSession):
            self._db.admin_sessions.delete_one({"_id": obj_id})
        self._identity_map.pop((type(obj), obj_id), None)


def get_db() -> Generator[DatabaseContext, None, None]:
    yield DatabaseContext()


def SessionLocal() -> DatabaseContext:
    return DatabaseContext()


def ensure_unique_session_names(db: Database) -> None:
    batches = list(db.batches.find().sort("created_at", 1))
    seen = set()
    counter = 1
    for b in batches:
        raw_name = b.get("name") or ""
        try:
            clean = clean_session_name(raw_name)
        except ValueError:
            clean = f"Session {counter}"
            counter += 1
        cand_norm = normalized_session_name(clean)
        candidate = clean
        suff = 2
        while cand_norm in seen:
            candidate = f"{clean} {suff}"
            cand_norm = normalized_session_name(candidate)
            suff += 1
        seen.add(cand_norm)
        db.batches.update_one(
            {"_id": b["_id"]},
            {"$set": {"name": candidate, "name_normalized": cand_norm}}
        )


def ensure_indexes(db: Database) -> None:
    try:
        ensure_unique_session_names(db)
        # batches collection
        db.batches.create_index([("name_normalized", ASCENDING)], unique=True)

        # participants collection
        db.participants.create_index([("batch_id", ASCENDING), ("normalized_email", ASCENDING)], unique=True)
        db.participants.create_index([("certificate_code", ASCENDING)], unique=True, sparse=True)
        db.participants.create_index([("idempotency_key", ASCENDING)], unique=True)
        db.participants.create_index([("batch_id", ASCENDING), ("is_current_import", ASCENDING)])
        db.participants.create_index([("status", ASCENDING)])

        # delivery attempts
        db.delivery_attempts.create_index([("participant_id", ASCENDING)])
        db.delivery_attempts.create_index([("participant_id", ASCENDING), ("attempt_number", DESCENDING)])

        # send records
        db.send_records.create_index([("reserved_at", DESCENDING)])
        db.send_records.create_index([("participant_id", ASCENDING)])
        db.send_records.create_index([("status", ASCENDING)])

        # admin credentials & sessions
        db.admin_users.create_index([("username", ASCENDING)], unique=True)
        db.admin_sessions.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    except Exception as exc:
        logger.warning("Index creation notice: %s", exc)


def ensure_default_admin(db: Database) -> None:
    settings = get_settings()
    existing = db.admin_users.find_one({"username": settings.superuser_username})
    if not existing:
        from .services.auth import hash_password
        pw_hash, salt = hash_password(settings.superuser_password)
        db.admin_users.insert_one({
            "_id": str(uuid.uuid4()),
            "username": settings.superuser_username,
            "password_hash": pw_hash,
            "salt": salt,
            "created_at": datetime.now(timezone.utc),
        })


def ensure_schema(db: Database | None = None) -> None:
    target_db = get_db_instance() if db is None else db
    ensure_indexes(target_db)
    ensure_default_admin(target_db)


# Backwards compatibility dummy for tests
class _Base:
    metadata = None

Base = _Base()
engine = None
