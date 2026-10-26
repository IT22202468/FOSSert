from datetime import datetime, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import Batch, Participant
from app.services.codes import generate_certificate_code
from app.services.fonts import resolve_font_path
from app.services.rendering import render_certificate

client = TestClient(app)


def test_login_and_auth_flow(clean_database):
    settings = get_settings()
    settings.auth_required = True

    # Attempt login with invalid password
    bad_login = client.post("/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
    assert bad_login.status_code == 401

    # Login with default superuser credentials
    login_resp = client.post("/api/auth/login", json={
        "username": settings.superuser_username,
        "password": settings.superuser_password,
    })
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "token" in data
    assert data["username"] == settings.superuser_username
    token = data["token"]

    # Verify /api/auth/me with Bearer token
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json() == {"authenticated": True, "username": settings.superuser_username}

    # Verify protected route with query param ?token=
    me_query_resp = client.get(f"/api/auth/me?token={token}")
    assert me_query_resp.status_code == 200
    assert me_query_resp.json() == {"authenticated": True, "username": settings.superuser_username}

    # Verify unauthenticated request is rejected
    unauth = client.get("/api/auth/me")
    assert unauth.status_code == 401

    # Verify batches route requires authentication
    batches_unauth = client.get("/api/batches")
    assert batches_unauth.status_code == 401

    batches_auth = client.get("/api/batches", headers={"Authorization": f"Bearer {token}"})
    assert batches_auth.status_code == 200

    # Logout
    logout_resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_resp.status_code == 200

    # Token is now revoked
    revoked = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert revoked.status_code == 401


def test_public_certificate_verification_and_download(clean_database, tmp_path):
    settings = get_settings()
    settings.auth_required = True

    # Non-existent code returns 404
    missing = client.get("/api/verify/FOSS-NOT-FOUND")
    assert missing.status_code == 404

    # Seed a batch and participant with generated certificate
    code = generate_certificate_code()
    template_path = tmp_path / "cert_template.png"
    Image.new("RGB", (800, 600), "white").save(template_path)

    render_result = render_certificate(
        template_path=template_path,
        font_path=resolve_font_path(None),
        output_dir=tmp_path,
        participant_id="part-123",
        name="Nipun Pramoditha",
        region={"x": 0.1, "y": 0.4, "w": 0.8, "h": 0.15, "font_size": 36, "min_font_size": 18, "alignment": "center"},
        certificate_code=code,
    )

    with SessionLocal() as db:
        batch = Batch(name="SLIIT FOSS Hackathon 2026", name_normalized="sliit foss hackathon 2026")
        db.add(batch)
        db.flush()

        participant = Participant(
            batch_id=batch.id,
            row_number=1,
            name="Nipun Pramoditha",
            email="nipun@example.com",
            normalized_email="nipun@example.com",
            canonical_email="nipun@example.com",
            is_valid=True,
            is_current_import=True,
            certificate_code=code,
            certificate_path=str(render_result.pdf_path),
            preview_path=str(render_result.preview_path),
            filename=render_result.filename,
            idempotency_key="cert-test-key-1",
        )
        db.add(participant)
        db.commit()

    # Public verification endpoint works without token
    resp = client.get(f"/api/verify/{code}")
    assert resp.status_code == 200
    info = resp.json()
    assert info["found"] is True
    assert info["certificate_code"] == code
    assert info["recipient_name"] == "Nipun Pramoditha"
    assert info["workshop_name"] == "SLIIT FOSS Hackathon 2026"
    assert info["issuer"] == "SLIIT FOSS Community"
    assert info["verified"] is True
    assert info["has_pdf"] is True
    assert info["has_preview"] is True

    # Case insensitivity test
    resp_lower = client.get(f"/api/verify/{code.lower()}")
    assert resp_lower.status_code == 200
    assert resp_lower.json()["certificate_code"] == code

    # Public preview image endpoint works without token
    preview_resp = client.get(f"/api/verify/{code}/preview")
    assert preview_resp.status_code == 200
    assert preview_resp.headers["content-type"] == "image/png"
    assert len(preview_resp.content) > 0

    # Public download PDF endpoint works without token
    download_resp = client.get(f"/api/verify/{code}/download")
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"] == "application/pdf"
    assert len(download_resp.content) > 0
