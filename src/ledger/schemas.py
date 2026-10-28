from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateAccount(BaseModel):
    name: str
    currency: str = "USD"
    allow_overdraft: bool = False


class AccountResponse(BaseModel):
    id: uuid.UUID
    name: str
    currency: str
    allow_overdraft: bool
    balance: int = Field(description="Balance in smallest currency unit (cents)")
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateTransfer(BaseModel):
    from_account_id: uuid.UUID
    to_account_id: uuid.UUID
    amount: int = Field(gt=0, description="Amount in smallest currency unit (cents)")
    description: str | None = None


class JournalEntryResponse(BaseModel):
    id: uuid.UUID
    transfer_id: uuid.UUID
    account_id: uuid.UUID
    entry_type: str
    amount: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TransferResponse(BaseModel):
    id: uuid.UUID
    idempotency_key: str | None
    description: str | None
    status: str
    entries: list[JournalEntryResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class ReconciliationResult(BaseModel):
    accounts_checked: int
    discrepancies: list[DiscrepancyDetail]
    global_debit_sum: int
    global_credit_sum: int
    balanced: bool


class DiscrepancyDetail(BaseModel):
    account_id: uuid.UUID
    cached_balance: int
    recomputed_balance: int
    drift: int


# Rebuild ReconciliationResult after DiscrepancyDetail is defined
ReconciliationResult.model_rebuild()
