from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ledger.models import Account, JournalEntry, Transfer

logger = logging.getLogger(__name__)


class InsufficientFunds(Exception):
    def __init__(self, account_id: uuid.UUID, balance: int, requested: int):
        self.account_id = account_id
        self.balance = balance
        self.requested = requested
        super().__init__(
            f"Account {account_id}: balance {balance}, requested {requested}"
        )


async def get_balance(session: AsyncSession, account_id: uuid.UUID) -> int:
    credits = (
        await session.execute(
            select(func.coalesce(func.sum(JournalEntry.amount), 0)).where(
                JournalEntry.account_id == account_id,
                JournalEntry.entry_type == "credit",
            )
        )
    ).scalar_one()
    debits = (
        await session.execute(
            select(func.coalesce(func.sum(JournalEntry.amount), 0)).where(
                JournalEntry.account_id == account_id,
                JournalEntry.entry_type == "debit",
            )
        )
    ).scalar_one()
    return int(credits) - int(debits)


async def create_transfer(
    session: AsyncSession,
    from_account_id: uuid.UUID,
    to_account_id: uuid.UUID,
    amount: int,
    idempotency_key: str | None = None,
    description: str | None = None,
) -> Transfer:
    if amount <= 0:
        raise ValueError("Transfer amount must be positive")
    if from_account_id == to_account_id:
        raise ValueError("Cannot transfer to the same account")

    # Idempotency: return existing transfer if key was already used.
    if idempotency_key:
        existing = (
            await session.execute(
                select(Transfer).where(
                    Transfer.idempotency_key == idempotency_key
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            logger.info("Idempotent hit for key=%s", idempotency_key)
            return existing

    # Lock both accounts in ID order to prevent deadlocks.
    ordered_ids = sorted([from_account_id, to_account_id])
    accounts: dict[uuid.UUID, Account] = {}
    for aid in ordered_ids:
        row = (
            await session.execute(
                select(Account)
                .where(Account.id == aid)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise ValueError(f"Account {aid} not found")
        accounts[aid] = row

    from_account = accounts[from_account_id]

    # Enforce balance constraint unless overdraft is allowed.
    if not from_account.allow_overdraft:
        balance = await get_balance(session, from_account_id)
        if balance < amount:
            raise InsufficientFunds(from_account_id, balance, amount)

    transfer = Transfer(
        idempotency_key=idempotency_key,
        description=description,
        status="completed",
    )
    session.add(transfer)
    await session.flush()

    debit = JournalEntry(
        transfer_id=transfer.id,
        account_id=from_account_id,
        entry_type="debit",
        amount=amount,
    )
    credit = JournalEntry(
        transfer_id=transfer.id,
        account_id=to_account_id,
        entry_type="credit",
        amount=amount,
    )
    session.add_all([debit, credit])
    await session.flush()

    logger.info(
        "Transfer %s: %d cents from %s to %s",
        transfer.id, amount, from_account_id, to_account_id,
    )
    return transfer


async def reverse_transfer(
    session: AsyncSession, transfer_id: uuid.UUID
) -> Transfer:
    original = (
        await session.execute(
            select(Transfer).where(Transfer.id == transfer_id)
        )
    ).scalar_one_or_none()
    if original is None:
        raise ValueError(f"Transfer {transfer_id} not found")
    if original.status == "reversed":
        raise ValueError(f"Transfer {transfer_id} is already reversed")

    entries = (
        await session.execute(
            select(JournalEntry).where(JournalEntry.transfer_id == transfer_id)
        )
    ).scalars().all()

    reversal = Transfer(
        description=f"Reversal of {transfer_id}",
        status="completed",
    )
    session.add(reversal)
    await session.flush()

    for entry in entries:
        reversed_type = "credit" if entry.entry_type == "debit" else "debit"
        session.add(
            JournalEntry(
                transfer_id=reversal.id,
                account_id=entry.account_id,
                entry_type=reversed_type,
                amount=entry.amount,
            )
        )

    original.status = "reversed"
    await session.flush()

    logger.info("Reversed transfer %s as %s", transfer_id, reversal.id)
    return reversal
