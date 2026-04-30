from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.chat import ChatSession, ChatMessage, MessageRole
from app.schemas.chat import (
    ChatSessionCreate,
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionResponse,
    ChatSessionSummary,
)
from app.services.claude_service import chat_with_ai

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: ChatSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = ChatSession(
        user_id=current_user.id,
        title=payload.title or "New Conversation",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=List[ChatSessionSummary])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    result = []
    for s in sessions:
        msg_count = db.query(ChatMessage).filter(ChatMessage.session_id == s.id).count()
        result.append(
            ChatSessionSummary(
                id=s.id,
                user_id=s.user_id,
                title=s.title,
                created_at=s.created_at,
                updated_at=s.updated_at,
                message_count=msg_count,
            )
        )
    return result


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )
    return session


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
def send_message(
    session_id: int,
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    # Save user message
    user_msg = ChatMessage(
        session_id=session_id,
        role=MessageRole.user,
        content=payload.content,
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    # Build conversation history
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    messages = [{"role": m.role.value, "content": m.content} for m in history]

    # Build personalised system context
    user_context_parts = [f"Patient name: {current_user.name}"]
    if current_user.age:
        user_context_parts.append(f"Age: {current_user.age}")
    if current_user.gender:
        user_context_parts.append(f"Gender: {current_user.gender}")
    if current_user.medical_history:
        user_context_parts.append(f"Medical history: {current_user.medical_history}")
    user_context = ". ".join(user_context_parts) + "."

    system_override = (
        "You are PainSync AI, an empathetic chronic pain management assistant. "
        "Be warm, supportive, and medically accurate. Never diagnose or prescribe. "
        "Always recommend consulting a healthcare professional for medical decisions. "
        "If the user describes emergency symptoms, advise calling emergency services immediately. "
        f"Patient context: {user_context}"
    )

    # Get AI response
    try:
        ai_response = chat_with_ai(messages, system=system_override)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI service temporarily unavailable: {str(e)}",
        )

    # Save assistant message
    assistant_msg = ChatMessage(
        session_id=session_id,
        role=MessageRole.assistant,
        content=ai_response,
    )
    db.add(assistant_msg)

    # Update session title from first user message if still default
    if session.title == "New Conversation" and len(history) == 1:
        session.title = payload.content[:80] + ("..." if len(payload.content) > 80 else "")

    db.commit()
    db.refresh(assistant_msg)
    return assistant_msg


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )
    db.delete(session)
    db.commit()
