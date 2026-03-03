from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Application
from app.utils.file_handler import move_temp_to_final, sanitize_filename, save_icon_file, save_upload_to_temp

settings = get_settings()
WINDOWS_PLATFORM = "windows"
LINUX_PLATFORM = "linux"
ALLOWED_FILE_TYPES_BY_PLATFORM = {
    WINDOWS_PLATFORM: {"msi", "exe"},
    LINUX_PLATFORM: {"deb", "tar.gz", "sh"},
}
ALLOWED_EXTENSIONS_BY_PLATFORM = {
    WINDOWS_PLATFORM: {".msi", ".exe"},
    LINUX_PLATFORM: {".deb", ".tar.gz", ".sh"},
}


def normalize_target_platform(value: Optional[str]) -> str:
    normalized = (value or WINDOWS_PLATFORM).strip().lower()
    if normalized not in ALLOWED_FILE_TYPES_BY_PLATFORM:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid target_platform")
    return normalized


async def create_application(
    db: Session,
    display_name: str,
    version: str,
    upload_file: UploadFile,
    description: Optional[str] = None,
    install_args: Optional[str] = None,
    uninstall_args: Optional[str] = None,
    is_visible_in_store: bool = True,
    category: Optional[str] = None,
    icon_file: Optional[UploadFile] = None,
    target_platform: str = WINDOWS_PLATFORM,
) -> Application:
    normalized_name = (display_name or "").strip()
    if not normalized_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="display_name is required")

    existing = (
        db.query(Application)
        .filter(func.lower(Application.display_name) == normalized_name.lower())
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Application name already exists",
        )

    normalized_platform = normalize_target_platform(target_platform)

    temp_path, digest_hex, total_size, file_type = await save_upload_to_temp(
        upload_file=upload_file,
        upload_dir=settings.upload_dir,
        max_upload_size=settings.max_upload_size,
        allowed_extensions=ALLOWED_EXTENSIONS_BY_PLATFORM[normalized_platform],
    )
    if file_type not in ALLOWED_FILE_TYPES_BY_PLATFORM[normalized_platform]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type for platform '{normalized_platform}'",
        )

    app = Application(
        display_name=normalized_name,
        description=description,
        filename="temp",
        original_filename=upload_file.filename,
        version=version,
        file_hash=f"sha256:{digest_hex}",
        file_size_bytes=total_size,
        file_type=file_type,
        target_platform=normalized_platform,
        install_args=install_args,
        uninstall_args=uninstall_args,
        is_visible_in_store=is_visible_in_store,
        category=category,
        is_active=True,
    )

    final_path: Optional[Path] = None
    icon_filename: Optional[str] = None
    try:
        db.add(app)
        db.flush()

        safe_filename = sanitize_filename(app.id, digest_hex, upload_file.filename or "")
        final_path = Path(settings.upload_dir) / safe_filename
        move_temp_to_final(temp_path, final_path)

        app.filename = safe_filename

        if icon_file is not None and icon_file.filename:
            icon_filename, icon_url = await save_icon_file(
                icon_file=icon_file,
                upload_dir=settings.upload_dir,
                max_icon_size=settings.max_icon_size,
                app_id=app.id,
            )
            app.icon_url = icon_url

        db.add(app)
        db.commit()
        db.refresh(app)
        return app
    except Exception:
        db.rollback()
        temp_path.unlink(missing_ok=True)
        if final_path and final_path.exists():
            final_path.unlink(missing_ok=True)
        if icon_filename:
            (Path(settings.upload_dir) / "icons" / icon_filename).unlink(missing_ok=True)
        raise


def list_applications(db: Session, only_active: bool = False) -> list[Application]:
    query = db.query(Application)
    if only_active:
        query = query.filter(Application.is_active.is_(True))
    return query.order_by(Application.created_at.desc()).all()


def get_application(db: Session, app_id: int) -> Application:
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return app


def update_application(
    db: Session,
    app_id: int,
    *,
    display_name: Optional[str] = None,
    version: Optional[str] = None,
    description: Optional[str] = None,
    install_args: Optional[str] = None,
    uninstall_args: Optional[str] = None,
    is_visible_in_store: Optional[bool] = None,
    category: Optional[str] = None,
    target_platform: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Application:
    app = get_application(db, app_id)
    if display_name is not None:
        normalized_name = display_name.strip()
        if not normalized_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="display_name is required")
        existing = (
            db.query(Application.id)
            .filter(
                Application.id != app.id,
                func.lower(Application.display_name) == normalized_name.lower(),
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application name already exists")
        app.display_name = normalized_name
    if version is not None:
        app.version = version
    if description is not None:
        app.description = description
    if install_args is not None:
        app.install_args = install_args
    if uninstall_args is not None:
        app.uninstall_args = uninstall_args
    if is_visible_in_store is not None:
        app.is_visible_in_store = is_visible_in_store
    if category is not None:
        app.category = category
    if target_platform is not None:
        normalized_platform = normalize_target_platform(target_platform)
        if app.file_type not in ALLOWED_FILE_TYPES_BY_PLATFORM[normalized_platform]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Existing file type '{app.file_type}' is incompatible with target_platform '{normalized_platform}'",
            )
        app.target_platform = normalized_platform
    if is_active is not None:
        app.is_active = is_active
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def delete_application(db: Session, app_id: int) -> None:
    app = get_application(db, app_id)
    file_path = Path(settings.upload_dir) / app.filename
    icon_path: Optional[Path] = None
    if app.icon_url and app.icon_url.startswith("/uploads/icons/"):
        icon_path = Path(settings.upload_dir) / "icons" / Path(app.icon_url).name
    db.delete(app)
    db.commit()
    file_path.unlink(missing_ok=True)
    if icon_path:
        icon_path.unlink(missing_ok=True)


async def update_application_icon(
    db: Session,
    app_id: int,
    *,
    icon_file: UploadFile,
) -> Application:
    app = get_application(db, app_id)
    old_icon_path: Optional[Path] = None
    if app.icon_url and app.icon_url.startswith("/uploads/icons/"):
        old_icon_path = Path(settings.upload_dir) / "icons" / Path(app.icon_url).name

    icon_filename, icon_url = await save_icon_file(
        icon_file=icon_file,
        upload_dir=settings.upload_dir,
        max_icon_size=settings.max_icon_size,
        app_id=app.id,
    )
    app.icon_url = icon_url
    db.add(app)
    db.commit()
    db.refresh(app)

    new_icon_path = Path(settings.upload_dir) / "icons" / icon_filename
    if old_icon_path and old_icon_path != new_icon_path:
        old_icon_path.unlink(missing_ok=True)
    return app


def remove_application_icon(db: Session, app_id: int) -> Application:
    app = get_application(db, app_id)
    old_icon_path: Optional[Path] = None
    if app.icon_url and app.icon_url.startswith("/uploads/icons/"):
        old_icon_path = Path(settings.upload_dir) / "icons" / Path(app.icon_url).name

    app.icon_url = None
    db.add(app)
    db.commit()
    db.refresh(app)

    if old_icon_path:
        old_icon_path.unlink(missing_ok=True)
    return app
