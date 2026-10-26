import os
from pathlib import Path

import mongomock
import pytest
from PIL import ImageFont

from app.config import get_settings
from app.database import ensure_schema, set_test_db

# Initialize test database early so test collection doesn't attempt to connect to live MongoDB
_mock_client = mongomock.MongoClient()
_mock_db = _mock_client["test_certloop"]
set_test_db(_mock_db)


@pytest.fixture(autouse=True)
def clean_database():
    mock_client = mongomock.MongoClient()
    mock_db = mock_client["test_certloop"]
    set_test_db(mock_db)
    ensure_schema(mock_db)

    settings = get_settings()
    settings.auth_required = False
    settings.max_emails_per_day = 200
    settings.email_send_delay_seconds = 0
    settings.min_email_send_delay_seconds = 0
    settings.max_email_send_delay_seconds = 120
    settings.healthy_sends_before_speedup = 5
    settings.smtp_connection_reuse = True
    settings.smtp_max_messages_per_connection = 25
    settings.smtp_workers = 1
    settings.smtp_timeout_seconds = 30
    settings.smtp_data_timeout_seconds = 300
    yield
    set_test_db(_mock_db)


@pytest.fixture
def font_path() -> Path:
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        pytest.skip("No system TrueType font is available for rendering tests")
    ImageFont.truetype(str(path), 12)
    return path
