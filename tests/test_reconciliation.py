from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_reconciliation_empty_ledger(client):
    recon = (await client.get("/reconciliation")).json()
    assert recon["balanced"] is True
    assert recon["global_debit_sum"] == recon["global_credit_sum"]


@pytest.mark.asyncio
async def test_reconciliation_after_transfers(client):
    a1 = (await client.post("/accounts", json={"name": "ReconS", "allow_overdraft": True})).json()
    a2 = (await client.post("/accounts", json={"name": "ReconR"})).json()

    for i in range(10):
        await client.post(
            "/transfers",
            json={"from_account_id": a1["id"], "to_account_id": a2["id"], "amount": 100 * (i + 1)},
        )

    recon = (await client.get("/reconciliation")).json()
    assert recon["balanced"] is True
    assert len(recon["discrepancies"]) == 0
