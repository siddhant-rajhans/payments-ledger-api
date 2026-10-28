from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_ledger_always_balances(client):
    """Create many accounts and transfers; global debits must equal global credits."""
    accounts = []
    for i in range(10):
        r = await client.post(
            "/accounts", json={"name": f"Prop-{i}", "allow_overdraft": True}
        )
        accounts.append(r.json()["id"])

    for i in range(50):
        src = accounts[i % len(accounts)]
        dst = accounts[(i * 7 + 3) % len(accounts)]
        if src == dst:
            dst = accounts[(i + 1) % len(accounts)]
        await client.post(
            "/transfers",
            json={"from_account_id": src, "to_account_id": dst, "amount": (i + 1) * 100},
        )

    recon = (await client.get("/reconciliation")).json()
    assert recon["balanced"] is True
    assert recon["global_debit_sum"] == recon["global_credit_sum"]
    assert len(recon["discrepancies"]) == 0


@pytest.mark.asyncio
async def test_reversals_restore_balance(client):
    """Transfer then reverse; both accounts return to zero."""
    a1 = (await client.post("/accounts", json={"name": "RevPropS", "allow_overdraft": True})).json()
    a2 = (await client.post("/accounts", json={"name": "RevPropR"})).json()

    transfers = []
    for i in range(5):
        r = await client.post(
            "/transfers",
            json={"from_account_id": a1["id"], "to_account_id": a2["id"], "amount": 1000},
        )
        transfers.append(r.json()["id"])

    for tid in transfers:
        await client.post(f"/transfers/{tid}/reverse")

    a1_bal = (await client.get(f"/accounts/{a1['id']}")).json()["balance"]
    a2_bal = (await client.get(f"/accounts/{a2['id']}")).json()["balance"]
    assert a1_bal == 0
    assert a2_bal == 0
