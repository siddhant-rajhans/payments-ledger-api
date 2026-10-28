from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ledger.database import get_session
from ledger.models import Transfer
from ledger.schemas import CreateTransfer, TransferResponse
from ledger.services.transfer import (
    InsufficientFunds,
    create_transfer,
    reverse_transfer,
)

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.post("", response_model=TransferResponse, status_code=201)
async def post_transfer(
    body: CreateTransfer,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
):
    try:
        async with session.begin():
            transfer = await create_transfer(
                session,
                from_account_id=body.from_account_id,
                to_account_id=body.to_account_id,
                amount=body.amount,
                idempotency_key=idempotency_key,
                description=body.description,
            )
            transfer_id = transfer.id

        result = (
            await session.execute(
                select(Transfer)
                .options(selectinload(Transfer.entries))
                .where(Transfer.id == transfer_id)
            )
        ).scalar_one()
        return TransferResponse.model_validate(result)

    except InsufficientFunds as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{transfer_id}", response_model=TransferResponse)
async def get_transfer(
    transfer_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    transfer = (
        await session.execute(
            select(Transfer)
            .options(selectinload(Transfer.entries))
            .where(Transfer.id == transfer_id)
        )
    ).scalar_one_or_none()
    if transfer is None:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return TransferResponse.model_validate(transfer)


@router.post("/{transfer_id}/reverse", response_model=TransferResponse, status_code=201)
async def post_reverse(
    transfer_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    try:
        async with session.begin():
            reversal = await reverse_transfer(session, transfer_id)
            reversal_id = reversal.id

        result = (
            await session.execute(
                select(Transfer)
                .options(selectinload(Transfer.entries))
                .where(Transfer.id == reversal_id)
            )
        ).scalar_one()
        return TransferResponse.model_validate(result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
