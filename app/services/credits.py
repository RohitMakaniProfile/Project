"""Credit system service: ledger-based balance, atomic deduction, idempotency."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models import CreditTransaction
from app.exceptions import InsufficientCreditsError, IdempotencyConflictError
from app.logging_config import get_logger

logger = get_logger(__name__)


async def get_balance(db: AsyncSession, org_id: uuid.UUID) -> int:
    """Compute current credit balance from the transaction ledger."""
    result = await db.execute(
        select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
            CreditTransaction.organisation_id == org_id
        )
    )
    return result.scalar_one()


async def get_recent_transactions(
    db: AsyncSession, org_id: uuid.UUID, limit: int = 10
) -> list[CreditTransaction]:
    """Return the most recent credit transactions for an organisation."""
    result = await db.execute(
        select(CreditTransaction)
        .where(CreditTransaction.organisation_id == org_id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def grant_credits(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    amount: int,
    reason: str,
) -> CreditTransaction:
    """Grant credits to an organisation (admin action)."""
    txn = CreditTransaction(
        id=uuid.uuid4(),
        organisation_id=org_id,
        user_id=user_id,
        amount=amount,
        reason=reason,
        created_at=datetime.now(timezone.utc),
    )
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    logger.info(
        "credits_granted",
        org_id=str(org_id),
        amount=amount,
        reason=reason,
    )
    return txn


async def check_and_get_existing_idempotent_response(
    db: AsyncSession,
    org_id: uuid.UUID,
    idempotency_key: str,
) -> Optional[CreditTransaction]:
    """
    Check if an idempotency key has already been used for this organisation.
    Returns the existing transaction if found, None otherwise.
    """
    result = await db.execute(
        select(CreditTransaction).where(
            CreditTransaction.idempotency_key == idempotency_key,
            CreditTransaction.organisation_id == org_id,
        )
    )
    return result.scalar_one_or_none()


async def deduct_credits(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    amount: int,
    reason: str,
    idempotency_key: Optional[str] = None,
) -> tuple[CreditTransaction, int]:
    """
    Atomically deduct credits from an organisation's balance.

    Uses SELECT ... FOR UPDATE to lock the organisation's rows in
    credit_transactions, preventing concurrent deductions from both
    succeeding when there are insufficient credits.

    If an idempotency_key is provided, the unique constraint on
    idempotency_key in the credit_transactions table prevents duplicate
    deductions at the database level.

    Returns (transaction, remaining_balance).
    Raises InsufficientCreditsError if balance is too low.
    Raises IdempotencyConflictError if the key has already been used.
    """
    if amount <= 0:
        raise ValueError("Deduction amount must be positive")

    # Lock rows then aggregate separately — PostgreSQL disallows FOR UPDATE
    # directly on aggregate queries. Lock the individual rows first via a
    # subquery, then sum them in the outer query.
    locked_rows = (
        select(CreditTransaction.amount)
        .where(CreditTransaction.organisation_id == org_id)
        .with_for_update()
        .subquery()
    )
    lock_result = await db.execute(
        select(func.coalesce(func.sum(locked_rows.c.amount), 0))
    )
    current_balance = lock_result.scalar_one()

    if current_balance < amount:
        raise InsufficientCreditsError(
            balance=current_balance, required=amount
        )

    txn = CreditTransaction(
        id=uuid.uuid4(),
        organisation_id=org_id,
        user_id=user_id,
        amount=-amount,
        reason=reason,
        idempotency_key=idempotency_key,
        created_at=datetime.now(timezone.utc),
    )
    db.add(txn)

    try:
        await db.flush()
    except IntegrityError as e:
        # The unique constraint on idempotency_key was violated —
        # this is a duplicate request.
        await db.rollback()
        if idempotency_key and "idempotency_key" in str(e.orig):
            raise IdempotencyConflictError(idempotency_key)
        raise

    remaining = current_balance - amount

    logger.info(
        "credits_deducted",
        org_id=str(org_id),
        amount=amount,
        remaining=remaining,
        reason=reason,
        idempotency_key=idempotency_key,
    )
    return txn, remaining


async def refund_credits(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    amount: int,
    reason: str,
) -> CreditTransaction:
    """Refund credits to an organisation (e.g., when a background job fails)."""
    txn = CreditTransaction(
        id=uuid.uuid4(),
        organisation_id=org_id,
        user_id=user_id,
        amount=amount,  # positive = refund
        reason=reason,
        created_at=datetime.now(timezone.utc),
    )
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    logger.info(
        "credits_refunded",
        org_id=str(org_id),
        amount=amount,
        reason=reason,
    )
    return txn
