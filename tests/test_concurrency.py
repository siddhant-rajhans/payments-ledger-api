from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_concurrent_transfers_no_drift(client):
    """Fire N parallel transfers between two accounts; final balances must match."""
    a1 = (await client.post("/accounts", json={"name": "ConcA", "allow_overdraft": True})).json()
    a2 = (await client.post("/accounts", json={"name": "ConcB", "allow_overdraft": True})).json()

    n = 50
    amount = 100

    async def transfer(i: int):
        return await client.post(
            "/transfers",
            json={
                "from_account_id": a1["id"],
                "to_account_id": a2["id"],
                "amount": amount,
            },
        )

    results = await asyncio.gather(*(transfer(i) for i in range(n)))
    succeeded = [r for r in results if r.status_code == 201]

    a1_bal = (await client.get(f"/accounts/{a1['id']}")).json()["balance"]
    a2_bal = (await client.get(f"/accounts/{a2['id']}")).json()["balance"]

    expected = len(succeeded) * amount
    assert a1_bal == -expected
    assert a2_bal == expected
    assert a1_bal + a2_bal == 0


@pytest.mark.asyncio
async def test_concurrent_transfers_insufficient_funds(client):
    """Start with a fixed balance; concurrent withdrawals must never overdraw."""
    sender = (await client.post("/accounts", json={"name": "LimitedSender"})).json()
    receiver = (await client.post("/accounts", json={"name": "LimitedReceiver", "allow_overdraft": True})).json()

    # Fund the sender with 1000 cents.
    funder = (await client.post("/accounts", json={"name": "Funder", "allow_overdraft": True})).json()
    await client.post(
        "/transfers",
        json={"from_account_id": funder["id"], "to_account_id": sender["id"], "amount": 1000},
    )

    # Fire 20 concurrent transfers of 100 each (only 10 should succeed).
    async def withdraw(i: int):
        return await client.post(
            "/transfers",
            json={
                "from_account_id": sender["id"],
                "to_account_id": receiver["id"],
                "amount": 100,
            },
        )

    results = await asyncio.gather(*(withdraw(i) for i in range(20)))
    succeeded = [r for r in results if r.status_code == 201]
    failed = [r for r in results if r.status_code == 422]

    sender_bal = (await client.get(f"/accounts/{sender['id']}")).json()["balance"]
    assert sender_bal >= 0, f"Balance went negative: {sender_bal}"
    assert len(succeeded) == 1000 // 100
    assert len(succeeded) + len(failed) == 20


@pytest.mark.asyncio
async def test_bidirectional_concurrent_transfers(client):
    """Two accounts send to each other simultaneously; net balance must be zero."""
    a1 = (await client.post("/accounts", json={"name": "BiA", "allow_overdraft": True})).json()
    a2 = (await client.post("/accounts", json={"name": "BiB", "allow_overdraft": True})).json()

    async def a_to_b(i: int):
        return await client.post(
            "/transfers",
            json={"from_account_id": a1["id"], "to_account_id": a2["id"], "amount": 50},
        )

    async def b_to_a(i: int):
        return await client.post(
            "/transfers",
            json={"from_account_id": a2["id"], "to_account_id": a1["id"], "amount": 50},
        )

    tasks = [a_to_b(i) for i in range(25)] + [b_to_a(i) for i in range(25)]
    await asyncio.gather(*tasks)

    a1_bal = (await client.get(f"/accounts/{a1['id']}")).json()["balance"]
    a2_bal = (await client.get(f"/accounts/{a2['id']}")).json()["balance"]
    assert a1_bal + a2_bal == 0
