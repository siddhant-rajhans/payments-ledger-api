from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ledger.database import get_session
from ledger.models import Account, JournalEntry
from ledger.schemas import AccountResponse, CreateAccount, JournalEntryResponse
from ledger.services.transfer import get_balance

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("", response_model=AccountResponse, status_code=201)
async def create_account(
    body: CreateAccount, session: AsyncSession = Depends(get_session)
):
    account = Account(
        name=body.name,
        currency=body.currency,
        allow_overdraft=body.allow_overdraft,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return AccountResponse(
        id=account.id,
        name=account.name,
        currency=account.currency,
        allow_overdraft=account.allow_overdraft,
        balance=0,
        created_at=account.created_at,
    )


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    account = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    balance = await get_balance(session, account_id)
    return AccountResponse(
        id=account.id,
        name=account.name,
        currency=account.currency,
        allow_overdraft=account.allow_overdraft,
        balance=balance,
        created_at=account.created_at,
    )


@router.get("/{account_id}/entries", response_model=list[JournalEntryResponse])
async def list_entries(
    account_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    account = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    entries = (
        await session.execute(
            select(JournalEntry)
            .where(JournalEntry.account_id == account_id)
            .order_by(JournalEntry.created_at)
        )
    ).scalars().all()
    return [JournalEntryResponse.model_validate(e) for e in entries]
