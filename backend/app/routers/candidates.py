from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/candidates", tags=["candidates"])


def _with_photos():
    return select(models.SimilarityCandidate).options(
        selectinload(models.SimilarityCandidate.photo_a).selectinload(models.Photo.references),
        selectinload(models.SimilarityCandidate.photo_b).selectinload(models.Photo.references),
    )


@router.get("", response_model=list[schemas.CandidateOut])
def list_candidates(status: str | None = None, db: Session = Depends(get_db)):
    q = _with_photos().order_by(models.SimilarityCandidate.phash_distance)
    if status:
        q = q.where(models.SimilarityCandidate.status == status)
    return db.scalars(q).all()


@router.post("/{candidate_id}/confirm", response_model=schemas.CandidateOut)
def confirm_candidate(candidate_id: int, db: Session = Depends(get_db)):
    cand = db.scalar(_with_photos().where(models.SimilarityCandidate.id == candidate_id))
    if not cand:
        raise HTTPException(404, "候选不存在")
    cand.status = "confirmed"
    cand.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(cand)
    return cand


@router.post("/{candidate_id}/reject", response_model=schemas.CandidateOut)
def reject_candidate(candidate_id: int, db: Session = Depends(get_db)):
    """误判处理：人工判定"不相似"，两张照片都保留，候选关闭不再出现。"""
    cand = db.scalar(_with_photos().where(models.SimilarityCandidate.id == candidate_id))
    if not cand:
        raise HTTPException(404, "候选不存在")
    cand.status = "rejected"
    cand.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(cand)
    return cand
