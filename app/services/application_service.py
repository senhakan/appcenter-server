from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Application
from app.utils.file_handler import move_temp_to_final, sanitize_filename, save_upload_to_temp

settings = get_settings()


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
) -> Application:
    temp_path, digest_hex, total_size, file_type = await save_upload_to_temp(
        upload_file=upload_file,
        upload_dir=settings.upload_dir,
        max_upload_size=settings.max_upload_size,
    )

    app = Application(
        display_name=display_name,
        description=description,
        filename="temp",
        original_filename=upload_file.filename,
        version=version,
        file_hash=f"sha256:{digest_hex}",
        file_size_bytes=total_size,
        file_type=file_type,
        install_args=install_args,
        uninstall_args=uninstall_args,
        is_visible_in_store=is_visible_in_store,
        category=category,
        is_active=True,
    )

    final_path: Optional[Path] = None
    try:
        db.add(app)
        db.flush()

        safe_filename = sanitize_filename(app.id, digest_hex, upload_file.filename or "")
        final_path = Path(settings.upload_dir) / safe_filename
        move_temp_to_final(temp_path, final_path)

        app.filename = safe_filename
        db.add(app)
        db.commit()
        db.refresh(app)
        return app
    except Exception:
        db.rollback()
        temp_path.unlink(missing_ok=True)
        if final_path and final_path.exists():
            final_path.unlink(missing_ok=True)
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


def delete_application(db: Session, app_id: int) -> None:
    app = get_application(db, app_id)
    file_path = Path(settings.upload_dir) / app.filename
    db.delete(app)
    db.commit()
    file_path.unlink(missing_ok=True)

