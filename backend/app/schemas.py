from datetime import datetime

from pydantic import BaseModel


class ReferenceOut(BaseModel):
    id: int
    project_name: str
    note: str
    needs_manual_review: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PhotoOut(BaseModel):
    id: int
    original_filename: str
    photographer: str
    license_scope: str
    width: int
    height: int
    file_size: int
    status: str
    phash: str
    created_at: datetime
    references: list[ReferenceOut] = []

    model_config = {"from_attributes": True}


class CandidateOut(BaseModel):
    id: int
    phash_distance: int
    dhash_distance: int
    status: str
    created_at: datetime
    reviewed_at: datetime | None
    photo_a: PhotoOut
    photo_b: PhotoOut

    model_config = {"from_attributes": True}


class MergeMemberOut(BaseModel):
    photo: PhotoOut

    model_config = {"from_attributes": True}


class MergeGroupOut(BaseModel):
    id: int
    primary_photo_id: int
    note: str
    status: str
    created_at: datetime
    undone_at: datetime | None
    members: list[MergeMemberOut]

    model_config = {"from_attributes": True}


class MergeRequest(BaseModel):
    photo_ids: list[int]
    primary_photo_id: int
    note: str = ""


class ReferenceRequest(BaseModel):
    project_name: str
    note: str = ""


class UndoResult(BaseModel):
    group: MergeGroupOut
    restored_photo_ids: list[int]
    # 归并之后新增的引用，撤销时需人工处理
    references_needing_manual_review: list[ReferenceOut]
