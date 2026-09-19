"""ORM 模型：原始文件索引、相似关系、引用项目、归并操作与撤销快照。"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base

# ---------------------------------------------------------------------------
# 原始文件索引
# ---------------------------------------------------------------------------


class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)          # 上传时的原始文件名
    stored_name = Column(String(255), nullable=False, unique=True)  # 本地落盘文件名
    thumb_name = Column(String(255), nullable=False)
    width = Column(Integer, nullable=False, default=0)
    height = Column(Integer, nullable=False, default=0)
    sha256 = Column(String(64), nullable=False, index=True)  # 字节级指纹（精确重复判定）
    phash = Column(String(16), nullable=False, index=True)   # 64bit 感知哈希，hex 存储
    photographer = Column(String(120), nullable=False)       # 摄影师署名
    license_scope = Column(String(40), nullable=False)       # 授权范围
    caption = Column(Text, nullable=False, default="")
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # 归并状态：未归并时 primary_id 指向自己；归并后指向主图
    primary_id = Column(Integer, ForeignKey("photos.id"), nullable=True)
    merged_at = Column(DateTime, nullable=True)
    # 当前所属的归并组（撤销时据此恢复；未归并/已撤销为 NULL）
    current_group_id = Column(Integer, ForeignKey("merge_records.id", use_alter=True), nullable=True)

    primary = relationship("Photo", remote_side=[id], foreign_keys=[primary_id])

    refs = relationship("PhotoRef", back_populates="photo", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# 引用项目（图库中“谁用了这张图”）
# ---------------------------------------------------------------------------


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    code = Column(String(40), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    refs = relationship("PhotoRef", back_populates="project", cascade="all, delete-orphan")


class PhotoRef(Base):
    """一条引用：项目在某处使用了某张照片。

    归并时只记录当时指向，不做物理改写；撤销时可以区分“归并前的老引用”
    （恢复原指向）与“归并之后产生的新引用”（必须人工处理）。
    """

    __tablename__ = "photo_refs"
    __table_args__ = (UniqueConstraint("project_id", "photo_id", "usage", name="uq_ref"),)

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    photo_id = Column(Integer, ForeignKey("photos.id"), nullable=False)
    usage = Column(String(200), nullable=False, default="内页插图")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    project = relationship("Project", back_populates="refs")
    photo = relationship("Photo", back_populates="refs")


# ---------------------------------------------------------------------------
# 相似候选（感知哈希接近只产生候选，人工确认前不做任何破坏性操作）
# ---------------------------------------------------------------------------


class SimilarityCandidate(Base):
    __tablename__ = "similarity_candidates"
    __table_args__ = (
        UniqueConstraint("photo_a_id", "photo_b_id", name="uq_candidate_pair"),
    )

    id = Column(Integer, primary_key=True)
    photo_a_id = Column(Integer, ForeignKey("photos.id"), nullable=False)
    photo_b_id = Column(Integer, ForeignKey("photos.id"), nullable=False)
    distance = Column(Integer, nullable=False)              # 汉明距离 0~64
    exact_duplicate = Column(Boolean, nullable=False, default=False)  # sha256 完全一致
    # pending / confirmed（已据此归并）/ rejected（人工判定为误判）
    status = Column(String(20), nullable=False, default="pending", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    decided_at = Column(DateTime, nullable=True)
    # 误判处理记录：审查人说明为什么这两张只是同场景不同照片
    reject_reason = Column(Text, nullable=False, default="")
    decided_by = Column(String(120), nullable=False, default="editor")

    photo_a = relationship("Photo", foreign_keys=[photo_a_id])
    photo_b = relationship("Photo", foreign_keys=[photo_b_id])


# ---------------------------------------------------------------------------
# 归并操作与撤销
# ---------------------------------------------------------------------------


class MergeRecord(Base):
    """一次归并操作。撤销时用 snapshot_json 恢复原有集合与引用指向。"""

    __tablename__ = "merge_records"

    id = Column(Integer, primary_key=True)
    primary_photo_id = Column(Integer, ForeignKey("photos.id"), nullable=False)
    member_ids = Column(Text, nullable=False)               # JSON: 归并时全部成员
    snapshot_json = Column(Text, nullable=False)            # JSON: 完整撤销快照
    note = Column(Text, nullable=False, default="")
    merged_by = Column(String(120), nullable=False, default="editor")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    undone_at = Column(DateTime, nullable=True)             # 非空 = 已撤销

    primary_photo = relationship("Photo", foreign_keys=[primary_photo_id])


# ---------------------------------------------------------------------------
# 操作审计（归并/撤销/误判判定等关键动作流水，便于追踪）
# ---------------------------------------------------------------------------


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    action = Column(String(40), nullable=False)
    detail = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
