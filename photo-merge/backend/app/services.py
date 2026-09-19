"""领域服务：相似候选生成、人工归并、撤销恢复。

关键业务规则：
1. pHash 距离 <= 阈值（或 sha256 完全一致）只生成 pending 候选，绝不自动删除/归并；
2. 授权范围 (license_scope) 不一致的照片禁止归并，即使字节完全相同；
3. 归并不删除任何原文件：成员的 primary_id 指向主图，引用链可解析到主图，
   原始摄影师署名、原文件、原引用全部保留；
4. 撤销按归并时的快照恢复原有集合；归并之后才产生的引用不能自动回退，
   作为 needs_manual_review 返回，交人工处理。
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import config
from .imaging import hamming_distance
from .models import AuditLog, MergeRecord, Photo, PhotoRef, SimilarityCandidate


class ServiceError(Exception):
    """业务规则冲突，由路由层转成 4xx。"""


def _log(db: Session, action: str, detail: str) -> None:
    db.add(AuditLog(action=action, detail=detail))


def _snapshot_ref(photo: Photo) -> dict:
    return {
        "id": photo.id,
        "primary_id": photo.primary_id,
        "merged_at": photo.merged_at.isoformat() if photo.merged_at else None,
        "current_group_id": photo.current_group_id,
    }


# ---------------------------------------------------------------------------
# 候选生成
# ---------------------------------------------------------------------------


def generate_candidates(db: Session, photo: Photo) -> list[SimilarityCandidate]:
    """新照片入库（或全量重扫）时，与其他“未归并主图”比较，生成候选。"""
    created: list[SimilarityCandidate] = []

    q = db.query(Photo).filter(
        Photo.id != photo.id,
        # 只和当前仍是主图身份的照片比较，避免与已归并的副本重复配对
        or_(Photo.primary_id == Photo.id, Photo.primary_id.is_(None)),
    )
    for other in q:
        a, b = sorted((photo.id, other.id))
        exists = (
            db.query(SimilarityCandidate)
            .filter_by(photo_a_id=a, photo_b_id=b)
            .first()
        )
        if exists:
            continue
        dist = hamming_distance(photo.phash, other.phash)
        exact = photo.sha256 == other.sha256
        if exact or dist <= config.PHASH_THRESHOLD:
            cand = SimilarityCandidate(
                photo_a_id=a,
                photo_b_id=b,
                distance=dist,
                exact_duplicate=exact,
            )
            db.add(cand)
            created.append(cand)
    db.flush()
    return created


# ---------------------------------------------------------------------------
# 人工审查：确认候选（走归并）/ 拒绝候选（误判记录）
# ---------------------------------------------------------------------------


def reject_candidate(db: Session, cand_id: int, reason: str) -> SimilarityCandidate:
    cand = db.get(SimilarityCandidate, cand_id)
    if not cand:
        raise ServiceError(404, "候选不存在")
    if cand.status != "pending":
        raise ServiceError(409, f"候选已结案（{cand.status}），不能再次判定")
    cand.status = "rejected"
    cand.reject_reason = reason.strip()
    cand.decided_at = datetime.utcnow()
    _log(
        db,
        "candidate_reject",
        f"候选 #{cand.id}（照片 {cand.photo_a_id}/{cand.photo_b_id}，距离 {cand.distance}）"
        f"被判误判：{cand.reject_reason}",
    )
    db.commit()
    db.refresh(cand)
    return cand


# ---------------------------------------------------------------------------
# 归并
# ---------------------------------------------------------------------------


def merge_photos(
    db: Session,
    photo_ids: list[int],
    primary_photo_id: int,
    note: str = "",
    candidate_id: int | None = None,
) -> MergeRecord:
    ids = sorted(set(photo_ids))
    if len(ids) < 2:
        raise ServiceError(422, "至少选择两张照片才能归并")
    if primary_photo_id not in ids:
        raise ServiceError(422, "主图必须在归并集合之内")

    members = db.query(Photo).filter(Photo.id.in_(ids)).all()
    if len(members) != len(ids):
        raise ServiceError(404, "存在已删除或无效的照片")

    # 所有成员必须是当前独立主图，不能把已经归并的副本二次归并
    for p in members:
        if p.primary_id not in (None, p.id):
            raise ServiceError(
                409,
                f"照片 #{p.id} 已归并到主图 #{p.primary_id}，请先撤销原归并",
            )

    # 规则红线：授权范围不一致，禁止直接合并
    scopes = {p.license_scope for p in members}
    if len(scopes) > 1:
        detail = "；".join(
            f"#{p.id}《{p.filename}》={p.license_scope}" for p in members
        )
        raise ServiceError(
            409,
            "授权范围不一致，禁止直接归并（" + detail + "）。请先统一授权，或判定为不同照片。",
        )

    now = datetime.utcnow()
    snapshot = {
        "photos": [_snapshot_ref(p) for p in members],
        "refs": [],
    }

    # 记录受影响引用的归并前指向，供撤销恢复
    ref_rows = (
        db.query(PhotoRef)
        .filter(PhotoRef.photo_id.in_(ids))
        .all()
    )
    for r in ref_rows:
        snapshot["refs"].append({"ref_id": r.id, "photo_id": r.photo_id})

    record = MergeRecord(
        primary_photo_id=primary_photo_id,
        member_ids=json.dumps(ids),
        snapshot_json=json.dumps(snapshot, ensure_ascii=False),
        note=note,
        created_at=now,
    )
    db.add(record)
    db.flush()

    primary = next(p for p in members if p.id == primary_photo_id)
    for p in members:
        if p.id == primary_photo_id:
            continue
        p.primary_id = primary_photo_id
        p.merged_at = now
        p.current_group_id = record.id
    primary.current_group_id = record.id

    # 候选结案
    confirmed_pairs = set()
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            confirmed_pairs.add((a, b) if a < b else (b, a))
    for cand in db.query(SimilarityCandidate).filter(
        SimilarityCandidate.status == "pending"
    ):
        pair = tuple(sorted((cand.photo_a_id, cand.photo_b_id)))
        if pair in confirmed_pairs:
            cand.status = "confirmed"
            cand.decided_at = now

    _log(
        db,
        "merge",
        f"归并组 #{record.id}：主图 #{primary_photo_id}，成员 {ids}，"
        f"授权={primary.license_scope}，备注={note}",
    )
    db.commit()
    db.refresh(record)
    return record


# ---------------------------------------------------------------------------
# 撤销
# ---------------------------------------------------------------------------


def undo_merge(db: Session, record_id: int) -> dict:
    record = db.get(MergeRecord, record_id)
    if not record:
        raise ServiceError(404, "归并记录不存在")
    if record.undone_at:
        raise ServiceError(409, "该归并已经撤销过")

    snapshot = json.loads(record.snapshot_json)
    merge_time = record.created_at

    # 1) 恢复照片原有集合
    restored_ids: list[int] = []
    for snap in snapshot["photos"]:
        photo = db.get(Photo, snap["id"])
        if not photo:
            continue
        photo.primary_id = snap["id"]          # 重新成为自己的主图
        photo.merged_at = None
        photo.current_group_id = None
        restored_ids.append(photo.id)

    # 2) 归并前已存在的引用 → 按快照恢复原指向
    old_ref_ids = {row["ref_id"] for row in snapshot["refs"]}
    for row in snapshot["refs"]:
        ref = db.get(PhotoRef, row["ref_id"])
        if ref:
            ref.photo_id = row["photo_id"]

    # 3) 归并之后产生的新引用（用户是通过主图引用的）→ 不自动回退，交人工处理
    member_ids = json.loads(record.member_ids)
    post_refs = (
        db.query(PhotoRef)
        .filter(
            PhotoRef.photo_id.in_(member_ids),
            PhotoRef.created_at > merge_time,
        )
        .all()
    )
    post_refs = [r for r in post_refs if r.id not in old_ref_ids]

    # 该组已确认的候选重新回到 pending，让编辑重新看一遍
    for cand in db.query(SimilarityCandidate).filter(
        SimilarityCandidate.status == "confirmed",
        SimilarityCandidate.decided_at >= merge_time,
    ):
        pair = {cand.photo_a_id, cand.photo_b_id}
        if pair.issubset(set(member_ids)):
            cand.status = "pending"
            cand.decided_at = None

    record.undone_at = datetime.utcnow()
    _log(
        db,
        "undo_merge",
        f"撤销归并组 #{record.id}，恢复照片 {restored_ids}；"
        f"归并后新引用 {[r.id for r in post_refs]} 需人工处理",
    )
    db.commit()
    return {"restored_photo_ids": restored_ids, "post_merge_refs": post_refs}


# ---------------------------------------------------------------------------
# 引用解析：跟随 primary_id 链走到当前主图
# ---------------------------------------------------------------------------


def resolve_ref(db: Session, ref_id: int) -> dict:
    ref = db.get(PhotoRef, ref_id)
    if not ref:
        raise ServiceError(404, "引用不存在")
    path = [ref.photo_id]
    current = db.get(Photo, ref.photo_id)
    seen = {current.id}
    while current.primary_id and current.primary_id != current.id:
        current = db.get(Photo, current.primary_id)
        if current.id in seen:
            break
        seen.add(current.id)
        path.append(current.id)
    return {
        "ref_id": ref.id,
        "original_photo_id": ref.photo_id if len(path) == 1 else path[0],
        "resolved_photo_id": path[-1],
        "hop_count": len(path) - 1,
        "path": path,
    }
