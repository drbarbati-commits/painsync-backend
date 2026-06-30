from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import StreamingResponse

from app.core.database import get_async_db
from app.core.deps import get_async_current_user
from app.models.user import User
from app.models.chat import ChatSession, ChatMessage, MessageRole
from app.schemas.chat import (
    ChatSessionCreate,
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionResponse,
    ChatSessionSummary,
)
from app.services.chat_service import assemble_context, generate_stream

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: ChatSessionCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
):
    session = ChatSession(
        user_id=current_user.id,
        title=payload.title or "New Conversation",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/sessions", response_model=List[ChatSessionSummary])
async def list_sessions(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = result.scalars().all()
    summaries = []
    for s in sessions:
        count_result = await db.execute(
            select(func.count(ChatMessage.id)).where(ChatMessage.session_id == s.id)
        )
        msg_count = count_result.scalar() or 0
        summaries.append(
            ChatSessionSummary(
                id=s.id,
                user_id=s.user_id,
                title=s.title,
                created_at=s.created_at,
                updated_at=s.updated_at,
                message_count=msg_count,
            )
        )
    return summaries


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalars().first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )
    return session


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
async def send_message(
    session_id: int,
    payload: ChatMessageCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalars().first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    user_msg = ChatMessage(
        session_id=session_id,
        role=MessageRole.user,
        content=payload.content,
    )
    db.add(user_msg)
    await db.commit()
    await db.refresh(user_msg)

    history_result = await db.execute(
        select(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    history = history_result.scalars().all()
    messages = [{"role": m.role.value, "content": m.content} for m in history]

    system = await assemble_context(current_user, db)

    try:
        stream = generate_stream(messages, system=system)
        full_response = ""
        async for chunk in stream:
            full_response += chunk
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI service temporarily unavailable: {e}",
        )

    assistant_msg = ChatMessage(
        session_id=session_id,
        role=MessageRole.assistant,
        content=full_response,
    )
    db.add(assistant_msg)

    if session.title == "New Conversation" and len(history) == 1:
        session.title = payload.content[:80] + ("..." if len(payload.content) > 80 else "")

    await db.commit()
    await db.refresh(assistant_msg)
    return assistant_msg


@router.post("/sessions/{session_id}/messages/stream")
async def send_message_stream(
    session_id: int,
    payload: ChatMessageCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalars().first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    user_msg = ChatMessage(
        session_id=session_id,
        role=MessageRole.user,
        content=payload.content,
    )
    db.add(user_msg)
    await db.commit()
    await db.refresh(user_msg)

    history_result = await db.execute(
        select(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    history = history_result.scalars().all()
    messages = [{"role": m.role.value, "content": m.content} for m in history]

    system = await assemble_context(current_user, db)

    async def event_stream():
        try:
            async for chunk in generate_stream(messages, system=system):
                yield f"data: {chunk}\n\n"
                if chunk is None:
                    break
        except Exception:
            yield f"data: [DONE]\n\n"
            return
        yield "data: [DONE]\n\n"

    if session.title == "New Conversation" and len(history) == 1:
        session.title = payload.content[:80] + ("..." if len(payload.content) > 80 else "")
    await db.commit()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalars().first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )
    await db.delete(session)
    await db.commit()
