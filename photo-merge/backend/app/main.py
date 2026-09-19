"""FastAPI 入口：上传、候选审查、归并、撤销、引用解析、审计页面接口。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import config, imaging
from .database import Base, engine, get_db
from .models import (
    AuditLog,
    MergeRecord,
    Photo,
    PhotoRef,
    Project,
    SimilarityCandidate,
)
from . import schemas
from . import services

Base.metadata.create_all(bind=engine)

app = FastAPI(title="图库相似照片人工归并系统", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 本地文件目录直接提供原图 / 缩略图访问
app.mount(
    "/media/originals",
    StaticFiles(directory=str(config.ORIGINAL_DIR)),
    name="originals",
)
app.mount(
    "/media/thumbs",
    StaticFiles(directory=str(config.THUMB_DIR)),
    name="thumbs",
)


# ---------------------------------------------------------------------------
# 序列化辅助
# ---------------------------------------------------------------------------


def _photo_out(p: Photo) -> schemas.PhotoOut:
    return schemas.PhotoOut(
        id=p.id,
        filename=p.filename,
        width=p.width,
        height=p.height,
        photographer=p.photographer,
        license_scope=p.license_scope,
        caption=p.caption,
        phash=p.phash,
        uploaded_at=p.uploaded_at,
        primary_id=p.primary_id if p.primary_id != p.id else None,
        merged_at=p.merged_at,
        current_group_id=p.current_group_id,
        thumb_url=f"/media/thumbs/{p.thumb_name}",
        original_url=f"/media/originals/{p.stored_name}",
    )


def _candidate_out(c: SimilarityCandidate) -> schemas.CandidateOut:
    return schemas.CandidateOut(
        id=c.id,
        photo_a=_photo_out(c.photo_a),
        photo_b=_photo_out(c.photo_b),
        distance=c.distance,
        exact_duplicate=c.exact_duplicate,
        status=c.status,
        reject_reason=c.reject_reason,
        created_at=c.created_at,
        decided_at=c.decided_at,
    )


def _ref_out(r: PhotoRef, merge_time: Optional[datetime] = None) -> schemas.RefOut:
    resolved = r.photo
    hops = 0
    seen = {resolved.id}
    while resolved.primary_id and resolved.primary_id != resolved.id:
        resolved = resolved.primary
        if resolved.id in seen:
            break
        seen.add(resolved.id)
        hops += 1
    return schemas.RefOut(
        id=r.id,
        project_id=r.project_id,
        project_code=r.project.code if r.project else "",
        project_name=r.project.name if r.project else "",
        photo_id=r.photo_id,
        resolved_photo_id=resolved.id,
        usage=r.usage,
        created_at=r.created_at,
        needs_manual_review=bool(merge_time and r.created_at > merge_time),
    )


def _merge_out(db: Session, rec: MergeRecord) -> schemas.MergeOut:
    ids = json.loads(rec.member_ids)
    members = db.query(Photo).filter(Photo.id.in_(ids)).order_by(Photo.id).all()
    return schemas.MergeOut(
        id=rec.id,
        primary_photo_id=rec.primary_photo_id,
        member_ids=ids,
        note=rec.note,
        created_at=rec.created_at,
        undone_at=rec.undone_at,
        members=[_photo_out(m) for m in members],
    )


# ---------------------------------------------------------------------------
# 上传（含裁剪 / 限尺寸 / JPEG 压缩），上传后立即计算候选
# ---------------------------------------------------------------------------


@app.post("/api/photos", response_model=schemas.PhotoDetail, tags=["photos"])
async def upload_photo(
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    photographer: str = Form("未署名"),
    license_scope: str = Form("internal"),
    caption: str = Form(""),
    crop: str = Form(""),  # 归一化裁剪框 JSON：{x,y,width,height}
):
    raw = await file.read()
    if not raw:
        raise HTTPException(422, "空文件")
    crop_dict = None
    if crop:
        try:
            crop_dict = json.loads(crop)
        except json.JSONDecodeError:
            raise HTTPException(422, "crop 必须是 JSON 坐标框")

    sha = imaging.sha256_bytes(raw)
    try:
        info = imaging.process_upload(raw, crop_dict)
    except Exception as exc:  # Pillow 无法识别等
        raise HTTPException(422, f"图像处理失败：{exc}")

    photo = Photo(
        filename=file.filename or info["stored_name"],
        stored_name=info["stored_name"],
        thumb_name=info["thumb_name"],
        width=info["width"],
        height=info["height"],
        sha256=sha,
        phash=info["phash"],
        photographer=photographer,
        license_scope=license_scope,
        caption=caption,
    )
    db.add(photo)
    db.flush()
    photo.primary_id = photo.id
    services.generate_candidates(db, photo)
    db.commit()
    db.refresh(photo)
    return _detail(db, photo)


def _detail(db: Session, photo: Photo) -> schemas.PhotoDetail:
    base = _photo_out(photo).model_dump()
    return schemas.PhotoDetail(
        **base,
        sha256=photo.sha256,
        stored_name=photo.stored_name,
        refs=[_ref_out(r) for r in photo.refs],
    )


@app.get("/api/photos", response_model=List[schemas.PhotoOut], tags=["photos"])
def list_photos(
    status: str = "all",  # all / active / merged
    db: Session = Depends(get_db),
):
    q = db.query(Photo)
    if status == "active":
        q = q.filter(or_(Photo.primary_id == Photo.id, Photo.primary_id.is_(None)))
    elif status == "merged":
        q = q.filter(Photo.primary_id != Photo.id)
    rows = q.order_by(Photo.uploaded_at.desc(), Photo.id.desc()).all()
    return [_photo_out(p) for p in rows]


@app.get("/api/photos/{photo_id}", response_model=schemas.PhotoDetail, tags=["photos"])
def photo_detail(photo_id: int, db: Session = Depends(get_db)):
    p = db.get(Photo, photo_id)
    if not p:
        raise HTTPException(404, "照片不存在")
    return _detail(db, p)


# ---------------------------------------------------------------------------
# 候选审查
# ---------------------------------------------------------------------------


@app.get("/api/candidates", response_model=List[schemas.CandidateOut], tags=["candidates"])
def list_candidates(status: str = "pending", db: Session = Depends(get_db)):
    rows = (
        db.query(SimilarityCandidate)
        .filter(SimilarityCandidate.status == status if status != "all" else True)
        .order_by(SimilarityCandidate.exact_duplicate.desc(), SimilarityCandidate.distance)
        .all()
    )
    return [_candidate_out(c) for c in rows]


@app.post("/api/candidates/{cid}/reject", response_model=schemas.CandidateOut, tags=["candidates"])
def reject_candidate(cid: int, body: schemas.RejectIn, db: Session = Depends(get_db)):
    try:
        cand = services.reject_candidate(db, cid, body.reason)
    except services.ServiceError as e:
        code, msg = e.args
        raise HTTPException(status_code=code, detail=msg)
    return _candidate_out(cand)


@app.post("/api/candidates/rescan", tags=["candidates"])
def rescan(db: Session = Depends(get_db)):
    """全量重扫：漏掉的候选（如调阈值后）重新生成。"""
    count_before = db.query(SimilarityCandidate).count()
    active = db.query(Photo).filter(
        or_(Photo.primary_id == Photo.id, Photo.primary_id.is_(None))
    ).all()
    made = 0
    for p in active:
        made += len(services.generate_candidates(db, p))
    db.commit()
    return {"created": made, "total_candidates": db.query(SimilarityCandidate).count()}


# ---------------------------------------------------------------------------
# 归并
# ---------------------------------------------------------------------------


@app.post("/api/merges", response_model=schemas.MergeOut, tags=["merges"])
def create_merge(body: schemas.MergeIn, db: Session = Depends(get_db)):
    try:
        rec = services.merge_photos(
            db,
            body.photo_ids,
            body.primary_photo_id,
            note=body.note,
            candidate_id=body.candidate_id,
        )
    except services.ServiceError as e:
        code, msg = e.args
        raise HTTPException(status_code=code, detail=msg)
    return _merge_out(db, rec)


@app.get("/api/merges", response_model=List[schemas.MergeOut], tags=["merges"])
def list_merges(include_undone: bool = True, db: Session = Depends(get_db)):
    q = db.query(MergeRecord)
    if not include_undone:
        q = q.filter(MergeRecord.undone_at.is_(None))
    rows = q.order_by(MergeRecord.created_at.desc()).all()
    return [_merge_out(db, r) for r in rows]


@app.get("/api/merges/{mid}", response_model=schemas.MergeOut, tags=["merges"])
def merge_detail(mid: int, db: Session = Depends(get_db)):
    rec = db.get(MergeRecord, mid)
    if not rec:
        raise HTTPException(404, "归并记录不存在")
    return _merge_out(db, rec)


@app.post("/api/merges/{mid}/undo", response_model=schemas.UndoResult, tags=["merges"])
def undo_merge(mid: int, db: Session = Depends(get_db)):
    rec = db.get(MergeRecord, mid)
    if not rec:
        raise HTTPException(404, "归并记录不存在")
    try:
        result = services.undo_merge(db, mid)
    except services.ServiceError as e:
        code, msg = e.args
        raise HTTPException(status_code=code, detail=msg)
    return schemas.UndoResult(
        merge_record_id=mid,
        restored_photo_ids=result["restored_photo_ids"],
        post_merge_refs=[_ref_out(r, merge_time=rec.created_at) for r in result["post_merge_refs"]],
        message=(
            "已恢复原有集合。注意：以下引用是归并之后新增的，系统无法自动判断应指向哪张原图，"
            "请人工处理。"
            if result["post_merge_refs"]
            else "已恢复原有集合，无归并后新增引用。"
        ),
    )


# ---------------------------------------------------------------------------
# 项目与引用（演示“选择主图后引用仍可追踪”）
# ---------------------------------------------------------------------------


@app.get("/api/projects", response_model=List[schemas.ProjectOut], tags=["projects"])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.id).all()


@app.post("/api/projects", response_model=schemas.ProjectOut, tags=["projects"])
def create_project(body: schemas.ProjectIn, db: Session = Depends(get_db)):
    if db.query(Project).filter_by(code=body.code).first():
        raise HTTPException(409, "项目编号已存在")
    proj = Project(code=body.code, name=body.name)
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


@app.post("/api/refs", response_model=schemas.RefOut, tags=["refs"])
def add_ref(body: schemas.RefIn, db: Session = Depends(get_db)):
    photo = db.get(Photo, body.photo_id)
    project = db.get(Project, body.project_id)
    if not photo or not project:
        raise HTTPException(404, "照片或项目不存在")
    exists = (
        db.query(PhotoRef)
        .filter_by(project_id=body.project_id, photo_id=body.photo_id, usage=body.usage)
        .first()
    )
    if exists:
        raise HTTPException(409, "该引用已存在")
    ref = PhotoRef(project_id=body.project_id, photo_id=body.photo_id, usage=body.usage)
    db.add(ref)
    db.commit()
    db.refresh(ref)
    return _ref_out(ref)


@app.get("/api/refs", response_model=List[schemas.RefOut], tags=["refs"])
def list_refs(db: Session = Depends(get_db)):
    rows = db.query(PhotoRef).order_by(PhotoRef.id).all()
    return [_ref_out(r) for r in rows]


@app.get("/api/refs/{rid}/resolve", response_model=schemas.ResolveOut, tags=["refs"])
def resolve_ref(rid: int, db: Session = Depends(get_db)):
    try:
        return services.resolve_ref(db, rid)
    except services.ServiceError as e:
        code, msg = e.args
        raise HTTPException(status_code=code, detail=msg)


class ReassignIn(BaseModel):
    photo_id: int


@app.patch("/api/refs/{rid}/reassign", response_model=schemas.RefOut, tags=["refs"])
def reassign_ref(rid: int, body: "ReassignIn", db: Session = Depends(get_db)):
    """撤销归并后，编辑对“归并之后的新引用”做出人工裁决：改指到某一张原图。"""
    ref = db.get(PhotoRef, rid)
    if not ref:
        raise HTTPException(404, "引用不存在")
    target = db.get(Photo, int(body.photo_id))
    if not target:
        raise HTTPException(404, "目标照片不存在")
    old = ref.photo_id
    ref.photo_id = target.id
    services._log(
        db,
        "ref_reassign",
        f"撤销后人工处理引用 #{ref.id}（{ref.usage}）：照片 #{old} -> #{target.id}",
    )
    db.commit()
    db.refresh(ref)
    return _ref_out(ref)


# ---------------------------------------------------------------------------
# 审计与元数据
# ---------------------------------------------------------------------------


@app.get("/api/audit", tags=["audit"])
def audit(limit: int = 100, db: Session = Depends(get_db)):
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return [
        {"id": r.id, "action": r.action, "detail": r.detail, "created_at": r.created_at}
        for r in rows
    ]


@app.get("/api/meta", tags=["meta"])
def meta():
    return {
        "phash_threshold": config.PHASH_THRESHOLD,
        "license_scopes": config.LICENSE_SCOPES,
        "max_dimension": config.MAX_DIMENSION,
        "jpeg_quality": config.JPEG_QUALITY,
        "database": config.DATABASE_URL.split("://")[0],
    }


@app.get("/healthz", tags=["meta"])
def healthz():
    return {"ok": True}


# ---------------------------------------------------------------------------
# 同源托管前端构建产物（vite build → frontend/dist），含 SPA 路由回退
# ---------------------------------------------------------------------------

_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith(("api/", "media/", "healthz")):
            raise HTTPException(404)
        target = _DIST / full_path
        if target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(_DIST / "index.html"))
