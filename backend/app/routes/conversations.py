import asyncio
import json
from contextlib import aclosing
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .. import llm
from ..config import PROVIDERS
from ..database import SessionLocal, get_db
from ..memory import build_context
from ..models import Conversation, Message, now
from ..schemas import ConversationCreate, ConversationOut, Generate, ImportData, MessageCreate, MessageOut

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def get_conversation(db: Session, id: UUID, *, lock=False) -> Conversation:
    query = select(Conversation).where(Conversation.id == id)
    if lock:
        query = query.with_for_update(nowait=True)
    try:
        conversation = db.scalar(query)
    except OperationalError:
        db.rollback()
        raise HTTPException(409, "This conversation is generating a response. Stop or wait before changing it.") from None
    if not conversation:
        raise HTTPException(404, "Conversation not found")
    return conversation


def ordered_messages(db: Session, id: UUID) -> list[Message]:
    return list(db.scalars(select(Message).where(Message.conversation_id == id).order_by(Message.sequence)))


@router.get("", response_model=list[ConversationOut])
def list_conversations(db: Session = Depends(get_db)):
    return db.scalars(select(Conversation).order_by(Conversation.updated_at.desc(), Conversation.id)).all()


@router.post("", response_model=ConversationOut, status_code=201)
def create_conversation(body: ConversationCreate, db: Session = Depends(get_db)):
    conversation = Conversation(title=body.title)
    db.add(conversation)
    db.commit()
    return conversation


def export_data(db: Session, conversations: list[Conversation]) -> dict:
    return {"format": "synapse", "version": 1, "conversations": [
        {**ConversationOut.model_validate(c).model_dump(mode="json"), "messages": [
            MessageOut.model_validate(m).model_dump(mode="json") for m in ordered_messages(db, c.id)
        ]} for c in conversations
    ]}


@router.get("/export")
def export_all(db: Session = Depends(get_db)):
    return export_data(db, list(db.scalars(select(Conversation).order_by(Conversation.created_at))))


@router.post("/import", response_model=list[ConversationOut], status_code=201)
def import_conversations(body: ImportData, db: Session = Depends(get_db)):
    created = []
    for imported in body.conversations:
        conversation = Conversation(title=imported.title)
        db.add(conversation)
        db.flush()
        for sequence, message in enumerate(imported.messages, start=1):
            db.add(Message(conversation_id=conversation.id, sequence=sequence, role=message.role,
                           content=message.content, provider=message.provider, model=message.model, status="completed"))
        created.append(conversation)
    db.commit()
    return created


@router.get("/{id}", response_model=ConversationOut)
def read_conversation(id: UUID, db: Session = Depends(get_db)):
    return get_conversation(db, id)


@router.patch("/{id}", response_model=ConversationOut)
def rename_conversation(id: UUID, body: ConversationCreate, db: Session = Depends(get_db)):
    conversation = get_conversation(db, id, lock=True)
    conversation.title = body.title
    conversation.updated_at = now()
    db.commit()
    return conversation


@router.delete("/{id}", status_code=204)
def delete_conversation(id: UUID, db: Session = Depends(get_db)):
    db.delete(get_conversation(db, id, lock=True))
    db.commit()
    return Response(status_code=204)


@router.get("/{id}/export")
def export_one(id: UUID, db: Session = Depends(get_db)):
    return export_data(db, [get_conversation(db, id)])


@router.get("/{id}/messages", response_model=list[MessageOut])
def list_messages(id: UUID, db: Session = Depends(get_db)):
    get_conversation(db, id)
    return ordered_messages(db, id)


@router.post("/{id}/messages", response_model=MessageOut, status_code=201)
def add_message(id: UUID, body: MessageCreate, db: Session = Depends(get_db)):
    conversation = get_conversation(db, id, lock=True)
    existing = db.get(Message, body.id)
    if existing:
        if existing.conversation_id != id or existing.role != "user" or existing.content != body.content:
            raise HTTPException(409, "Message ID already used with different content")
        return existing
    messages = ordered_messages(db, id)
    if messages and messages[-1].role == "user":
        raise HTTPException(409, "Generate a response to the last message before adding another.")
    message = Message(id=body.id, conversation_id=id, sequence=messages[-1].sequence + 1 if messages else 1,
                      role="user", content=body.content, status="completed")
    db.add(message)
    if not messages and conversation.title == "New conversation":
        conversation.title = body.content[:70]
    conversation.updated_at = now()
    db.commit()
    return message


def event(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data)}\n\n"


@router.post("/{id}/generate")
def generate(id: UUID, body: Generate, request: Request, db: Session = Depends(get_db)):
    get_conversation(db, id)
    if body.provider not in PROVIDERS:
        raise HTTPException(422, "Unknown provider")
    try:
        llm.completion_options(db, body.provider, body.model)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None

    async def stream():
        # Hold a PostgreSQL row lock throughout generation. Concurrent writers fail
        # quickly; cancellation rolls back, leaving the stored history intact.
        with SessionLocal() as session:
            try:
                conversation = get_conversation(session, id, lock=True)
                existing = session.get(Message, body.id)
                if existing:
                    if existing.conversation_id != id or existing.role != "assistant" or existing.provider != body.provider or existing.model != body.model:
                        raise HTTPException(409, "Generation ID already used")
                    yield event("done", {"message": MessageOut.model_validate(existing).model_dump(mode="json")})
                    return
                messages = ordered_messages(session, id)
                replaced = None
                if body.regenerate and messages and messages[-1].role == "assistant":
                    replaced = messages.pop()
                if not messages or messages[-1].role != "user":
                    raise HTTPException(409, "Send a message first, or regenerate the last assistant response.")
                context, metadata = build_context(session, messages)
                options = llm.completion_options(session, body.provider, body.model)
                yield event("context", metadata)
                parts = []
                length = 0
                async with aclosing(llm.stream_completion(options, context)) as completion:
                    async for chunk in completion:
                        if await request.is_disconnected():
                            return
                        parts.append(chunk)
                        length += len(chunk)
                        if length > 1_000_000:
                            raise RuntimeError("Response too large")
                        yield event("delta", {"text": chunk})
                if not parts or await request.is_disconnected():
                    if not parts:
                        yield event("error", {"message": "Provider returned an empty response. Try another model or retry."})
                    return
                if replaced:
                    session.delete(replaced)
                    session.flush()
                assistant = Message(id=body.id, conversation_id=id, sequence=messages[-1].sequence + 1,
                                    role="assistant", content="".join(parts), provider=body.provider, model=body.model, status="completed")
                session.add(assistant)
                conversation.updated_at = now()
                session.commit()
                yield event("done", {"message": MessageOut.model_validate(assistant).model_dump(mode="json")})
            except asyncio.CancelledError:
                raise
            except HTTPException as error:
                yield event("error", {"message": error.detail})
            except ValueError:
                # Only context/configuration errors generated locally are exposed.
                yield event("error", {"message": "Context or provider configuration is invalid. Check Settings and message size."})
            except Exception as error:
                yield event("error", {"message": llm.safe_error(error)})

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
