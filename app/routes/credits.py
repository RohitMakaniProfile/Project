"""Credit system routes: grant and balance."""
import uuid
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import User
from app.schemas import (
    CreditBalanceResponse,
    CreditGrantRequest,
    CreditTransactionOut,
)
from app.services.credits import get_balance, get_recent_transactions, grant_credits
from app.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/credits", tags=["credits"])


@router.post("/grant")
async def grant(
    request: Request,
    body: CreditGrantRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """POST /credits/grant — admin only. Adds credits to the organisation."""
    txn = await grant_credits(
        db=db,
        org_id=user.organisation_id,
        user_id=user.id,
        amount=body.amount,
        reason=body.reason,
    )
    balance = await get_balance(db, user.organisation_id)
    return {
        "message": f"Granted {body.amount} credits",
        "balance": balance,
        "transaction_id": str(txn.id),
    }


@router.get("/balance", response_model=CreditBalanceResponse)
async def balance(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GET /credits/balance — returns organisation credit balance and last 10 transactions."""
    current_balance = await get_balance(db, user.organisation_id)
    transactions = await get_recent_transactions(db, user.organisation_id, limit=10)
    return CreditBalanceResponse(
        organisation_id=user.organisation_id,
        balance=current_balance,
        recent_transactions=[
            CreditTransactionOut.model_validate(t) for t in transactions
        ],
    )
