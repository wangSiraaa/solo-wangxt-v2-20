from datetime import datetime

from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Photo(Base):
    """原始文件索引：每张上传的图片一行，文件本身落在本地目录。"""

    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True)
    photographer: Mapped[str] = mapped_column(String(120))
    license_scope: Mapped[str] = mapped_column(String(32))  # editorial / commercial / internal
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    file_size: Mapped[int] = mapped_column(Integer)
    ahash: Mapped[str] = mapped_column(String(16))
    dhash: Mapped[str] = mapped_column(String(16))
    phash: Mapped[str] = mapped_column(String(16))
    # active: 在库可用；merged: 已被归并（文件保留，可追踪、可撤销）
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    references: Mapped[list["PhotoReference"]] = relationship(
        back_populates="photo", cascade="all, delete-orphan"
    )


class PhotoReference(Base):
    """引用项目：追踪某张照片被哪些项目引用。归并不删除引用。"""

    __tablename__ = "photo_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id"))
    project_name: Mapped[str] = mapped_column(String(200))
    note: Mapped[str] = mapped_column(Text, default="")
    # 撤销归并时，归并期间新增的引用会被标记为需人工处理
    needs_manual_review: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    photo: Mapped[Photo] = relationship(back_populates="references")


class SimilarityCandidate(Base):
    """相似候选：哈希接近只产生候选记录，需人工确认/驳回，绝不自动删图。"""

    __tablename__ = "similarity_candidates"
    __table_args__ = (UniqueConstraint("photo_a_id", "photo_b_id", name="uq_candidate_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_a_id: Mapped[int] = mapped_column(ForeignKey("photos.id"))
    photo_b_id: Mapped[int] = mapped_column(ForeignKey("photos.id"))
    phash_distance: Mapped[int] = mapped_column(Integer)
    dhash_distance: Mapped[int] = mapped_column(Integer)
    # pending: 待审查；confirmed: 人工确认相似；rejected: 人工判定误判
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    photo_a: Mapped[Photo] = relationship(foreign_keys=[photo_a_id])
    photo_b: Mapped[Photo] = relationship(foreign_keys=[photo_b_id])


class MergeGroup(Base):
    """一次归并操作。撤销时恢复原有集合，组记录保留用于审计。"""

    __tablename__ = "merge_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    primary_photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / undone
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    primary_photo: Mapped[Photo] = relationship(foreign_keys=[primary_photo_id])
    members: Mapped[list["MergeMember"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class MergeMember(Base):
    __tablename__ = "merge_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("merge_groups.id"))
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id"))

    group: Mapped[MergeGroup] = relationship(back_populates="members")
    photo: Mapped[Photo] = relationship()
