"""归并领域的核心规则，路由层只做参数解析与响应组装。"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .config import DHASH_THRESHOLD, PHASH_THRESHOLD
from .hashing import hamming


def generate_candidates(db: Session, photo: models.Photo) -> list[models.SimilarityCandidate]:
    """新照片入库后，与库中所有 active 照片比对哈希，接近的生成候选。

    只生成候选记录，绝不修改/删除任何已有照片。
    """
    others = db.scalars(
        select(models.Photo).where(models.Photo.id != photo.id, models.Photo.status == "active")
    ).all()
    created = []
    for other in others:
        pd = hamming(photo.phash, other.phash)
        dd = hamming(photo.dhash, other.dhash)
        if pd <= PHASH_THRESHOLD or dd <= DHASH_THRESHOLD:
            a, b = sorted([photo.id, other.id])
            exists = db.scalar(
                select(models.SimilarityCandidate).where(
                    models.SimilarityCandidate.photo_a_id == a,
                    models.SimilarityCandidate.photo_b_id == b,
                )
            )
            if not exists:
                cand = models.SimilarityCandidate(
                    photo_a_id=a, photo_b_id=b, phash_distance=pd, dhash_distance=dd
                )
                db.add(cand)
                created.append(cand)
    db.commit()
    return created


def _confirmed_pair_exists(db: Session, x: int, y: int) -> bool:
    a, b = sorted([x, y])
    return db.scalar(
        select(models.SimilarityCandidate).where(
            models.SimilarityCandidate.photo_a_id == a,
            models.SimilarityCandidate.photo_b_id == b,
            models.SimilarityCandidate.status == "confirmed",
        )
    ) is not None


def create_merge(db: Session, photo_ids: list[int], primary_id: int, note: str) -> models.MergeGroup:
    if primary_id not in photo_ids:
        raise HTTPException(422, "主图必须包含在归并集合中")
    if len(set(photo_ids)) < 2:
        raise HTTPException(422, "归并至少需要两张照片")

    photos = {
        p.id: p
        for p in db.scalars(select(models.Photo).where(models.Photo.id.in_(photo_ids))).all()
    }
    missing = set(photo_ids) - set(photos)
    if missing:
        raise HTTPException(404, f"照片不存在: {sorted(missing)}")

    not_active = [p.id for p in photos.values() if p.status != "active"]
    if not_active:
        raise HTTPException(409, f"照片 {not_active} 已被归并，不能重复归并")

    # 授权范围不同不允许直接合并
    scopes = {p.license_scope for p in photos.values()}
    if len(scopes) > 1:
        detail = {
            str(p.id): p.license_scope for p in photos.values()
        }
        raise HTTPException(
            409,
            f"授权范围不一致（{detail}），不允许直接合并；请先确认授权后再操作",
        )

    # 每张非主图都必须与主图存在"人工确认过"的候选，保证哈希接近只是候选、归并必经人工
    unconfirmed = [
        pid for pid in photo_ids if pid != primary_id and not _confirmed_pair_exists(db, pid, primary_id)
    ]
    if unconfirmed:
        raise HTTPException(
            409,
            f"照片 {unconfirmed} 与主图之间没有已人工确认的相似候选，不能归并",
        )

    group = models.MergeGroup(primary_photo_id=primary_id, note=note)
    db.add(group)
    db.flush()
    for pid in photo_ids:
        db.add(models.MergeMember(group_id=group.id, photo_id=pid))
        if pid != primary_id:
            photos[pid].status = "merged"
    db.commit()
    db.refresh(group)
    return group


def undo_merge(db: Session, group_id: int):
    """撤销归并：恢复原有集合；归并期间新增的引用标记为需人工处理。"""
    group = db.get(models.MergeGroup, group_id)
    if not group:
        raise HTTPException(404, "归并记录不存在")
    if group.status == "undone":
        raise HTTPException(409, "该归并已撤销过")

    member_ids = [m.photo_id for m in group.members]
    photos = {
        p.id: p
        for p in db.scalars(select(models.Photo).where(models.Photo.id.in_(member_ids))).all()
    }
    restored = []
    for pid, photo in photos.items():
        if photo.status == "merged":
            photo.status = "active"
            restored.append(pid)

    # 归并之后（group.created_at 起）新增到任一成员照片上的引用 → 提示人工处理
    new_refs = db.scalars(
        select(models.PhotoReference).where(
            models.PhotoReference.photo_id.in_(member_ids),
            models.PhotoReference.created_at >= group.created_at,
        )
    ).all()
    for ref in new_refs:
        ref.needs_manual_review = True

    group.status = "undone"
    group.undone_at = datetime.utcnow()
    db.commit()
    db.refresh(group)
    return group, restored, new_refs
