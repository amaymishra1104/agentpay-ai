from datetime import datetime, timezone

from sqlalchemy import func

from app.db.database import SessionLocal
from app.db.models import AgentMessage, AgentSession


def get_or_create_session(
    session_id: str,
    customer_id: str | None = None,
) -> AgentSession:
    db = SessionLocal()
    try:
        session = db.get(AgentSession, session_id)

        if session is not None:
            if customer_id is not None and session.customer_id != customer_id:
                if session.customer_id is None:
                    session.customer_id = customer_id
                    session.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    db.commit()
                    db.refresh(session)
                    return session
                raise ValueError(
                    f"Session {session_id} belongs to a different customer."
                )
            return session

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        session = AgentSession(
            session_id=session_id,
            customer_id=customer_id,
            created_at=now,
            updated_at=now,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_session(session_id: str) -> AgentSession | None:
    db = SessionLocal()
    try:
        return db.get(AgentSession, session_id)
    finally:
        db.close()


def save_message(
    session_id: str,
    role: str,
    content: str,
    message_type: str = "text",
    tool_name: str | None = None,
    tool_call_id: str | None = None,
) -> AgentMessage:
    db = SessionLocal()
    try:
        session = db.get(AgentSession, session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found.")

        last_sequence = db.query(
            func.max(AgentMessage.sequence)
        ).filter(
            AgentMessage.session_id == session_id
        ).scalar()

        message = AgentMessage(
            session_id=session_id,
            sequence=(last_sequence or 0) + 1,
            role=role,
            message_type=message_type,
            content=content,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        )
        session.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(message)
        db.commit()
        db.refresh(message)
        return message
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_messages(session_id: str) -> list[AgentMessage]:
    db = SessionLocal()
    try:
        return list(
            db.query(AgentMessage)
            .filter(AgentMessage.session_id == session_id)
            .order_by(AgentMessage.sequence.asc())
            .all()
        )
    finally:
        db.close()


def update_cart_id(
    session_id: str,
    cart_id: str,
) -> AgentSession:
    db = SessionLocal()
    try:
        session = db.get(AgentSession, session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found.")

        session.cart_id = cart_id
        session.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        db.refresh(session)
        return session
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()