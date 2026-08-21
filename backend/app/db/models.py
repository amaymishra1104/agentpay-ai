from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    actor: Mapped[str] = mapped_column(String(100), index=True)
    details: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    merchant_id: Mapped[str] = mapped_column(String(100), index=True)
    customer_id: Mapped[str] = mapped_column(String(100), index=True)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    status: Mapped[str] = mapped_column(String(50), default="active")
    subtotal_inr: Mapped[int] = mapped_column(Integer, default=0)
    discount_inr: Mapped[int] = mapped_column(Integer, default=0)
    shipping_inr: Mapped[int] = mapped_column(Integer, default=0)
    total_inr: Mapped[int] = mapped_column(Integer, default=0)
    applied_offers_json: Mapped[str] = mapped_column(String(2000), default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # selectin loading works well for many-to-one or one-to-many relationships in async/sync setups
    items: Mapped[list["CartItem"]] = relationship(
        "CartItem", back_populates="cart", cascade="all, delete-orphan", lazy="selectin"
    )



class CartItem(Base):
    __tablename__ = "cart_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    cart_id: Mapped[str] = mapped_column(String(100), ForeignKey("carts.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit_price_inr: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_inr: Mapped[int] = mapped_column(Integer, nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    inventory_checked: Mapped[bool] = mapped_column(Boolean, default=True)

    cart: Mapped["Cart"] = relationship("Cart", back_populates="items")


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    session_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(
        String(100),
        index=True,
        nullable=True,
    )
    cart_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    messages: Mapped[list["AgentMessage"]] = relationship(
        "AgentMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentMessage.sequence",
    )


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    session_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("agent_sessions.session_id"),
        index=True,
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    tool_call_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    session: Mapped["AgentSession"] = relationship(
        "AgentSession",
        back_populates="messages",
    )

