import secrets
from datetime import datetime, timezone


def generate_certificate_code(year: int | None = None) -> str:
    """Generate an official unique certificate code.
    Format: FOSS-<YEAR>-<PART1>-<PART2> (e.g., FOSS-2026-A8B4-9F2C)
    """
    current_year = year or datetime.now(timezone.utc).year
    part1 = secrets.token_hex(2).upper()
    part2 = secrets.token_hex(2).upper()
    return f"FOSS-{current_year}-{part1}-{part2}"
