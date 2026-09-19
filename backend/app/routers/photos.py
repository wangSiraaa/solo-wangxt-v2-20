import os
import uuid
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas, services
from ..config import LICENSE_SCOPES, STORAGE_DIR
from ..database import get_db
from ..hashing import compute_hashes

router = APIRouter(prefix="/api/photos", tags=["photos"])


def _photo_query():
    return select(models.Photo).options(selectinload(models.Photo.references))


@router.get("", response_model=list[schemas.PhotoOut])
def list_photos(status: str | None = None, db: Session = Depends(get_db)):
    q = _photo_query().order_by(models.Photo.id)
    if status:
        q = q.where(models.Photo.status == status)
    return db.scalars(q).all()


@router.get("/{photo_id}", response_model=schemas.PhotoOut)
def get_photo(photo_id: int, db: Session = Depends(get_db)):
    photo = db.scalar(_photo_query().where(models.Photo.id == photo_id))
    if not photo:
        raise HTTPException(404, "照片不存在")
    return photo


@router.get("/{photo_id}/file")
def get_photo_file(photo_id: int, db: Session = Depends(get_db)):
    photo = db.get(models.Photo, photo_id)
    if not photo:
        raise HTTPException(404, "照片不存在")
    path = os.path.join(STORAGE_DIR, photo.stored_filename)
    if not os.path.exists(path):
        raise HTTPException(404, "文件缺失")
    return FileResponse(path)


@router.post("/upload", response_model=schemas.PhotoOut, status_code=201)
async def upload_photo(
    file: UploadFile = File(...),
    photographer: str = Form(...),
    license_scope: str = Form(...),
    project_name: str = Form(""),
    db: Session = Depends(get_db),
):
    if license_scope not in LICENSE_SCOPES:
        raise HTTPException(422, f"授权范围必须是 {LICENSE_SCOPES} 之一")

    data = await file.read()
    try:
        img = Image.open(BytesIO(data))
        img.verify()
        img = Image.open(BytesIO(data))
    except Exception:
        raise HTTPException(422, "无法识别的图像文件")

    ext = os.path.splitext(file.filename or "upload.jpg")[1].lower() or ".jpg"
    stored = f"{uuid.uuid4().hex}{ext}"
    os.makedirs(STORAGE_DIR, exist_ok=True)
    with open(os.path.join(STORAGE_DIR, stored), "wb") as f:
        f.write(data)

    hashes = compute_hashes(data)
    photo = models.Photo(
        original_filename=file.filename or stored,
        stored_filename=stored,
        photographer=photographer,
        license_scope=license_scope,
        width=img.width,
        height=img.height,
        file_size=len(data),
        status="active",
        **hashes,
    )
    db.add(photo)
    db.flush()

    if project_name:
        db.add(models.PhotoReference(photo_id=photo.id, project_name=project_name))
    db.commit()

    # 哈希接近只产生候选，等待人工审查
    services.generate_candidates(db, photo)
    return db.scalar(_photo_query().where(models.Photo.id == photo.id))


@router.post("/{photo_id}/references", response_model=schemas.ReferenceOut, status_code=201)
def add_reference(photo_id: int, body: schemas.ReferenceRequest, db: Session = Depends(get_db)):
    photo = db.get(models.Photo, photo_id)
    if not photo:
        raise HTTPException(404, "照片不存在")
    ref = models.PhotoReference(
        photo_id=photo_id, project_name=body.project_name, note=body.note
    )
    db.add(ref)
    db.commit()
    db.refresh(ref)
    return ref
