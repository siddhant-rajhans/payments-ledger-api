from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_idempotent_transfer(client):
    a1 = (await client.post("/accounts", json={"name": "IdempS", "allow_overdraft": True})).json()
    a2 = (await client.post("/accounts", json={"name": "IdempR"})).json()

    payload = {
        "from_account_id": a1["id"],
        "to_account_id": a2["id"],
        "amount": 1000,
    }
    headers = {"Idempotency-Key": "test-key-001"}

    r1 = await client.post("/transfers", json=payload, headers=headers)
    r2 = await client.post("/transfers", json=payload, headers=headers)

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]

    balance = (await client.get(f"/accounts/{a2['id']}")).json()["balance"]
    assert balance == 1000


@pytest.mark.asyncio
async def test_idempotent_retry_storm(client):
    """Fire the same idempotency key many times; balance must reflect exactly one transfer."""
    a1 = (await client.post("/accounts", json={"name": "StormS", "allow_overdraft": True})).json()
    a2 = (await client.post("/accounts", json={"name": "StormR"})).json()

    payload = {
        "from_account_id": a1["id"],
        "to_account_id": a2["id"],
        "amount": 500,
    }
    headers = {"Idempotency-Key": "storm-key-001"}

    transfer_ids = set()
    for _ in range(20):
        r = await client.post("/transfers", json=payload, headers=headers)
        assert r.status_code == 201
        transfer_ids.add(r.json()["id"])

    assert len(transfer_ids) == 1
    balance = (await client.get(f"/accounts/{a2['id']}")).json()["balance"]
    assert balance == 500


@pytest.mark.asyncio
async def test_different_keys_create_separate_transfers(client):
    a1 = (await client.post("/accounts", json={"name": "DiffKeyS", "allow_overdraft": True})).json()
    a2 = (await client.post("/accounts", json={"name": "DiffKeyR"})).json()

    payload = {
        "from_account_id": a1["id"],
        "to_account_id": a2["id"],
        "amount": 100,
    }

    r1 = await client.post("/transfers", json=payload, headers={"Idempotency-Key": "key-a"})
    r2 = await client.post("/transfers", json=payload, headers={"Idempotency-Key": "key-b"})

    assert r1.json()["id"] != r2.json()["id"]
    balance = (await client.get(f"/accounts/{a2['id']}")).json()["balance"]
    assert balance == 200
