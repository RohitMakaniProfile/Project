from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


# ─── Error Response ───────────────────────────────────────────────
class ErrorResponse(BaseModel):
    error: str
    message: str
    request_id: str


# ─── Health ───────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: str
    database: str
    timestamp: str


# ─── Auth ─────────────────────────────────────────────────────────
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ─── User / Organisation ─────────────────────────────────────────
class OrganisationOut(BaseModel):
    id: UUID
    name: str
    slug: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: UUID
    email: str
    name: str
    role: str
    organisation_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    user: UserOut
    organisation: OrganisationOut


# ─── Credits ──────────────────────────────────────────────────────
class CreditGrantRequest(BaseModel):
    amount: int = Field(..., gt=0, description="Number of credits to grant (positive integer)")
    reason: str = Field(..., min_length=1, max_length=500)


class CreditTransactionOut(BaseModel):
    id: UUID
    amount: int
    reason: str
    created_at: datetime
    user_id: Optional[UUID] = None

    model_config = {"from_attributes": True}


class CreditBalanceResponse(BaseModel):
    organisation_id: UUID
    balance: int
    recent_transactions: List[CreditTransactionOut]


# ─── Product Endpoints ────────────────────────────────────────────
class AnalyseRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=2000)


class AnalyseResponse(BaseModel):
    result: str
    credits_remaining: int


class SummariseRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=2000)


class SummariseResponse(BaseModel):
    job_id: UUID
    credits_remaining: int


class JobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime


# ─── Credit Error ─────────────────────────────────────────────────
class InsufficientCreditsResponse(BaseModel):
    error: str = "insufficient_credits"
    balance: int
    required: int
