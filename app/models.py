import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    Index,
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    member = "member"


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class Organisation(Base):
    __tablename__ = "organisations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    users = relationship("User", back_populates="organisation", lazy="selectin")
    credit_transactions = relationship(
        "CreditTransaction", back_populates="organisation", lazy="selectin"
    )
    jobs = relationship("Job", back_populates="organisation", lazy="selectin")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    google_id = Column(String(255), nullable=False, unique=True, index=True)
    organisation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.member)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    organisation = relationship("Organisation", back_populates="users")


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    amount = Column(Integer, nullable=False)  # positive = credit, negative = debit
    reason = Column(Text, nullable=False)
    idempotency_key = Column(String(255), nullable=True, unique=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    organisation = relationship("Organisation", back_populates="credit_transactions")
    user = relationship("User")

    __table_args__ = (
        Index("ix_credit_transactions_org_created", "organisation_id", "created_at"),
        Index(
            "ix_credit_transactions_idempotency",
            "idempotency_key",
            unique=True,
            postgresql_where=Column("idempotency_key").isnot(None),
        ),
    )


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status = Column(
        SAEnum(JobStatus), nullable=False, default=JobStatus.pending
    )
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    input_text = Column(Text, nullable=False)
    credit_transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("credit_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    idempotency_key = Column(String(255), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    organisation = relationship("Organisation", back_populates="jobs")
