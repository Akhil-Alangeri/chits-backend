"""Durable company logos on Cloud Run; filesystem storage for local development."""
import os
import re
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads"
LOGO_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
LOGO_NAME = re.compile(r"company_[0-9a-f]{32}\.(png|jpg|webp)")


def _bucket():
    name = os.getenv("COMPANY_LOGO_BUCKET", "").strip()
    if name:
        from google.cloud import storage
        return storage.Client().bucket(name)
    if os.getenv("K_SERVICE"):
        raise HTTPException(503, "Company logo storage is not configured.")
    return None


def save_logo(contents: bytes, content_type: str) -> str:
    filename = f"company_{uuid4().hex}{LOGO_TYPES[content_type]}"
    bucket = _bucket()
    if bucket is not None:
        bucket.blob(f"company-logos/{filename}").upload_from_string(
            contents, content_type=content_type, if_generation_match=0, timeout=30,
        )
    else:
        directory = UPLOAD_ROOT / "company-logos"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / filename).write_bytes(contents)
    return f"/uploads/company-logos/{filename}"


def read_logo(filename: str) -> bytes:
    if not LOGO_NAME.fullmatch(filename):
        raise HTTPException(404, "Logo not found.")
    bucket = _bucket()
    if bucket is not None:
        from google.api_core.exceptions import NotFound
        try:
            return bucket.blob(f"company-logos/{filename}").download_as_bytes(timeout=30)
        except NotFound:
            raise HTTPException(404, "Logo not found.") from None
    try:
        return (UPLOAD_ROOT / "company-logos" / filename).read_bytes()
    except FileNotFoundError:
        raise HTTPException(404, "Logo not found.") from None
