from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas, services
from ..database import get_db

router = APIRouter(prefix="/api/merges", tags=["merges"])


def _with_members():
    return select(models.MergeGroup).options(
        selectinload(models.MergeGroup.members)
        .selectinload(models.MergeMember.photo)
        .selectinload(models.Photo.references)
    )


@router.get("", response_model=list[schemas.MergeGroupOut])
def list_merges(db: Session = Depends(get_db)):
    return db.scalars(_with_members().order_by(models.MergeGroup.id.desc())).all()


@router.post("", response_model=schemas.MergeGroupOut, status_code=201)
def create_merge(body: schemas.MergeRequest, db: Session = Depends(get_db)):
    group = services.create_merge(db, body.photo_ids, body.primary_photo_id, body.note)
    return db.scalar(_with_members().where(models.MergeGroup.id == group.id))


@router.post("/{group_id}/undo", response_model=schemas.UndoResult)
def undo_merge(group_id: int, db: Session = Depends(get_db)):
    group, restored, new_refs = services.undo_merge(db, group_id)
    return schemas.UndoResult(
        group=db.scalar(_with_members().where(models.MergeGroup.id == group.id)),
        restored_photo_ids=restored,
        references_needing_manual_review=new_refs,
    )
