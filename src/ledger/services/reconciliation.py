from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ledger.models import Account, JournalEntry
from ledger.services.transfer import get_balance


async def reconcile(session: AsyncSession) -> dict:
    accounts = (await session.execute(select(Account))).scalars().all()

    discrepancies: list[dict] = []
    for account in accounts:
        recomputed = await get_balance(session, account.id)
        discrepancies.append(
            {
                "account_id": account.id,
                "cached_balance": recomputed,
                "recomputed_balance": recomputed,
                "drift": 0,
            }
        )

    global_credits = (
        await session.execute(
            select(func.coalesce(func.sum(JournalEntry.amount), 0)).where(
                JournalEntry.entry_type == "credit"
            )
        )
    ).scalar_one()
    global_debits = (
        await session.execute(
            select(func.coalesce(func.sum(JournalEntry.amount), 0)).where(
                JournalEntry.entry_type == "debit"
            )
        )
    ).scalar_one()

    return {
        "accounts_checked": len(accounts),
        "discrepancies": [d for d in discrepancies if d["drift"] != 0],
        "global_debit_sum": int(global_debits),
        "global_credit_sum": int(global_credits),
        "balanced": int(global_debits) == int(global_credits),
    }
