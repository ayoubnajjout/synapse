from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Memory, now
from ..schemas import MemoryCreate, MemoryOut, MemoryPatch

router = APIRouter(prefix="/api/memories", tags=["memories"])


@router.get("", response_model=list[MemoryOut])
def list_memories(db: Session = Depends(get_db)):
    return db.scalars(select(Memory).order_by(Memory.created_at, Memory.id)).all()


@router.post("", response_model=MemoryOut, status_code=201)
def add_memory(body: MemoryCreate, db: Session = Depends(get_db)):
    memory = Memory(**body.model_dump())
    db.add(memory)
    db.commit()
    return memory


@router.patch("/{id}", response_model=MemoryOut)
def edit_memory(id: UUID, body: MemoryPatch, db: Session = Depends(get_db)):
    memory = db.get(Memory, id)
    if not memory:
        raise HTTPException(404, "Memory not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(memory, key, value)
    memory.updated_at = now()
    db.commit()
    return memory


@router.delete("/{id}", status_code=204)
def delete_memory(id: UUID, db: Session = Depends(get_db)):
    memory = db.get(Memory, id)
    if not memory:
        raise HTTPException(404, "Memory not found")
    db.delete(memory)
    db.commit()
    return Response(status_code=204)


@router.delete("", status_code=204)
def clear_memories(db: Session = Depends(get_db)):
    db.execute(delete(Memory))
    db.commit()
    return Response(status_code=204)
