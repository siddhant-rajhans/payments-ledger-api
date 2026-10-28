from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ledger.database import get_session
from ledger.schemas import ReconciliationResult
from ledger.services.reconciliation import reconcile

router = APIRouter(tags=["reconciliation"])


@router.get("/reconciliation", response_model=ReconciliationResult)
async def run_reconciliation(session: AsyncSession = Depends(get_session)):
    result = await reconcile(session)
    return ReconciliationResult(**result)
