"""Pydantic 请求 / 响应模型。"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class PhotoOut(BaseModel):
    id: int
    filename: str
    width: int
    height: int
    photographer: str
    license_scope: str
    caption: str
    phash: str
    uploaded_at: datetime
    primary_id: Optional[int]
    merged_at: Optional[datetime]
    current_group_id: Optional[int]
    thumb_url: str
    original_url: str

    class Config:
        from_attributes = True


class PhotoDetail(PhotoOut):
    sha256: str
    stored_name: str
    refs: List["RefOut"] = []


class CandidateOut(BaseModel):
    id: int
    photo_a: PhotoOut
    photo_b: PhotoOut
    distance: int
    exact_duplicate: bool
    status: str
    reject_reason: str
    created_at: datetime
    decided_at: Optional[datetime]

    class Config:
        from_attributes = True


class RejectIn(BaseModel):
    reason: str = Field(..., min_length=2, max_length=500)


class MergeIn(BaseModel):
    candidate_id: Optional[int] = None
    photo_ids: List[int] = Field(..., min_length=2)
    primary_photo_id: int
    note: str = ""


class MergeOut(BaseModel):
    id: int
    primary_photo_id: int
    member_ids: List[int]
    note: str
    created_at: datetime
    undone_at: Optional[datetime]
    members: List[PhotoOut] = []


class UndoResult(BaseModel):
    merge_record_id: int
    restored_photo_ids: List[int]
    post_merge_refs: List["RefOut"]
    message: str


class ProjectIn(BaseModel):
    code: str
    name: str


class ProjectOut(BaseModel):
    id: int
    code: str
    name: str

    class Config:
        from_attributes = True


class RefIn(BaseModel):
    project_id: int
    photo_id: int
    usage: str = "内页插图"


class RefOut(BaseModel):
    id: int
    project_id: int
    project_code: str = ""
    project_name: str = ""
    photo_id: int
    resolved_photo_id: Optional[int] = None  # 跟随归并解析后的主图
    usage: str
    created_at: datetime
    needs_manual_review: bool = False        # 归并后产生的新引用，撤销时需人工处理


class ResolveOut(BaseModel):
    ref_id: int
    original_photo_id: int
    resolved_photo_id: int
    hop_count: int
    path: List[int]


PhotoDetail.model_rebuild()
UndoResult.model_rebuild()
