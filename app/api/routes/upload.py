"""
upload.py — Profile image upload endpoint.

Strategy:
1. If SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY are both set → upload to Supabase Storage bucket "avatars"
2. Otherwise → resize image to 256×256, encode as base64 data URL, store directly in users.avatar_url

This ensures the feature works even without Supabase Storage configured.
"""
import os
import uuid
import base64
import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/upload", tags=["Upload"])

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
BUCKET = "avatars"

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_SIZE_MB = 5
THUMB_SIZE = 256  # px — for base64 fallback, keep it small


def _resize_to_base64(contents: bytes, content_type: str) -> str:
    """Resize image to THUMB_SIZE×THUMB_SIZE and return as base64 data URL."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(contents))
        img = img.convert("RGB")
        img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"
    except Exception:
        # Pillow not available — encode raw bytes as-is
        b64 = base64.b64encode(contents).decode("utf-8")
        return f"data:{content_type};base64,{b64}"


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Upload a profile avatar image and return its public URL (or base64 data URL)."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: jpeg, png, webp, gif.",
        )

    contents = await file.read()

    if len(contents) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {MAX_SIZE_MB} MB.",
        )

    # ── Try Supabase Storage first ────────────────────────────────────────────
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
        ext = ext_map.get(file.content_type, "jpg")
        filename = f"user_{current_user.id}/{uuid.uuid4().hex}.{ext}"
        storage_url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{filename}"
        headers = {
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": file.content_type,
            "x-upsert": "true",
        }
        try:
            import httpx
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(storage_url, content=contents, headers=headers)
            if resp.status_code in (200, 201):
                public_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{filename}"
                return JSONResponse({"url": public_url})
            # Fall through to base64 if Supabase returns an error
        except Exception:
            pass  # Fall through to base64

    # ── Fallback: base64 data URL stored directly in avatar_url column ────────
    data_url = _resize_to_base64(contents, file.content_type)
    return JSONResponse({"url": data_url})
