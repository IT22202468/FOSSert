import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import get_settings
from ..database import get_db
from ..models import AdminSession, AdminUser

security = HTTPBearer(auto_error=False)


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Derives a salted PBKDF2-HMAC-SHA256 password hash."""
    salt = salt or secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    ).hex()
    return pw_hash, salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """Verifies a password against the stored salt and hash."""
    expected_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(expected_hash, password_hash)


def create_admin_session(db: Any, user: AdminUser, duration_hours: int = 72) -> tuple[str, datetime]:
    """Creates a new durable admin session token."""
    token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(hours=duration_hours)
    session_obj = AdminSession(token=token, user_id=user.id, expires_at=expires)
    db.admin_sessions.insert_one(session_obj.to_doc())
    return token, expires


def revoke_admin_session(db: Any, token: str) -> bool:
    """Revokes an existing admin session token."""
    res = db.admin_sessions.delete_one({"_id": token})
    return bool(res.deleted_count > 0)


def get_current_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(security),
    db: Any = Depends(get_db),
) -> AdminUser:
    """Dependency that enforces superuser authentication via Bearer token or ?token= query parameter."""
    settings = get_settings()
    if not settings.auth_required:
        dummy_doc = db.admin_users.find_one()
        if dummy_doc:
            return AdminUser.from_doc(dummy_doc)
        return AdminUser(
            id="test-admin",
            username="admin",
            password_hash="test",
            salt="test",
        )

    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials.strip()
    elif "token" in request.query_params:
        token = request.query_params["token"].strip()

    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    now = datetime.now(timezone.utc)
    session_doc = db.admin_sessions.find_one({"_id": token})
    if not session_doc:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    session = AdminSession.from_doc(session_doc)
    exp = session.expires_at
    if exp:
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
    user_doc = db.admin_users.find_one({"_id": session.user_id})
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")
    return AdminUser.from_doc(user_doc)


def get_optional_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(security),
    db: Any = Depends(get_db),
) -> AdminUser | None:
    """Optional dependency that returns the admin user if authenticated, else None."""
    try:
        return get_current_admin(request, credentials, db)
    except HTTPException:
        return None
