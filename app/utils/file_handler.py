from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Optional
from uuid import uuid4

import aiofiles
from fastapi import HTTPException, UploadFile, status

ALLOWED_EXTENSIONS = {".msi", ".exe"}
ALLOWED_ICON_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
READ_CHUNK_SIZE = 1024 * 1024  # 1MB


def ensure_upload_dir(upload_dir: str) -> Path:
    path = Path(upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def sanitize_filename(app_id: int, file_hash_hex: str, original_filename: str) -> str:
    ext = get_extension(original_filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only .msi and .exe allowed.",
        )
    safe_hash = re.sub(r"[^a-f0-9]", "", file_hash_hex.lower())[:8]
    return f"{app_id}_{safe_hash}{ext}"


async def save_upload_to_temp(
    upload_file: UploadFile,
    upload_dir: str,
    max_upload_size: int,
) -> tuple[Path, str, int, str]:
    ext = get_extension(upload_file.filename or "")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only .msi and .exe allowed.",
        )

    base_path = ensure_upload_dir(upload_dir)
    temp_path = base_path / f"temp_{uuid4().hex}{ext}"
    hash_sha256 = hashlib.sha256()
    total_size = 0

    try:
        async with aiofiles.open(temp_path, "wb") as out_file:
            while True:
                chunk = await upload_file.read(READ_CHUNK_SIZE)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_upload_size:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="File too large. Max 2GB.",
                    )
                await out_file.write(chunk)
                hash_sha256.update(chunk)
    except Exception:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise
    finally:
        await upload_file.close()

    return temp_path, hash_sha256.hexdigest(), total_size, ext.lstrip(".")


def move_temp_to_final(temp_path: Path, final_path: Path) -> None:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temp_path, final_path)


async def save_icon_file(
    icon_file: UploadFile,
    upload_dir: str,
    max_icon_size: int,
    app_id: int,
) -> tuple[str, str]:
    ext = get_extension(icon_file.filename or "")
    if ext not in ALLOWED_ICON_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid icon type. Allowed: .png, .jpg, .jpeg, .webp, .svg",
        )

    icons_dir = ensure_upload_dir(str(Path(upload_dir) / "icons"))
    safe_name = f"app_{app_id}_{uuid4().hex[:12]}{ext}"
    temp_path = icons_dir / f"temp_{uuid4().hex}{ext}"
    final_path = icons_dir / safe_name
    total_size = 0

    try:
        async with aiofiles.open(temp_path, "wb") as out_file:
            while True:
                chunk = await icon_file.read(READ_CHUNK_SIZE)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_icon_size:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Icon too large. Max 5MB.",
                    )
                await out_file.write(chunk)
        move_temp_to_final(temp_path, final_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise
    finally:
        await icon_file.close()

    return safe_name, f"/uploads/icons/{safe_name}"


def parse_range_header(range_header: Optional[str], file_size: int) -> Optional[tuple[int, int]]:
    if not range_header:
        return None
    if not range_header.startswith("bytes="):
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid range")

    raw = range_header.replace("bytes=", "", 1).strip()
    if "," in raw:
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Multiple ranges not supported")

    try:
        start_str, end_str = raw.split("-", 1)
        if start_str == "":
            suffix_len = int(end_str)
            if suffix_len <= 0:
                raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid range")
            start = max(file_size - suffix_len, 0)
            end = file_size - 1
        else:
            start = int(start_str)
            end = int(end_str) if end_str else file_size - 1
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid range") from exc

    if start < 0 or end >= file_size or start > end:
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid range")
    return start, end
