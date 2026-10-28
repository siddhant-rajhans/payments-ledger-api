from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_transfer(client):
    a1 = (await client.post("/accounts", json={"name": "Alice", "allow_overdraft": True})).json()
    a2 = (await client.post("/accounts", json={"name": "Bob"})).json()

    resp = await client.post(
        "/transfers",
        json={
            "from_account_id": a1["id"],
            "to_account_id": a2["id"],
            "amount": 5000,
            "description": "Test transfer",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "completed"
    assert len(data["entries"]) == 2

    alice = (await client.get(f"/accounts/{a1['id']}")).json()
    bob = (await client.get(f"/accounts/{a2['id']}")).json()
    assert alice["balance"] == -5000
    assert bob["balance"] == 5000


@pytest.mark.asyncio
async def test_insufficient_funds_rejected(client):
    a1 = (await client.post("/accounts", json={"name": "Sender"})).json()
    a2 = (await client.post("/accounts", json={"name": "Receiver"})).json()

    resp = await client.post(
        "/transfers",
        json={
            "from_account_id": a1["id"],
            "to_account_id": a2["id"],
            "amount": 100,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_overdraft_allowed(client):
    a1 = (await client.post("/accounts", json={"name": "OD-Sender", "allow_overdraft": True})).json()
    a2 = (await client.post("/accounts", json={"name": "OD-Receiver"})).json()

    resp = await client.post(
        "/transfers",
        json={
            "from_account_id": a1["id"],
            "to_account_id": a2["id"],
            "amount": 99999,
        },
    )
    assert resp.status_code == 201
    alice = (await client.get(f"/accounts/{a1['id']}")).json()
    assert alice["balance"] == -99999


@pytest.mark.asyncio
async def test_self_transfer_rejected(client):
    a1 = (await client.post("/accounts", json={"name": "SelfSend", "allow_overdraft": True})).json()
    resp = await client.post(
        "/transfers",
        json={
            "from_account_id": a1["id"],
            "to_account_id": a1["id"],
            "amount": 100,
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_reverse_transfer(client):
    a1 = (await client.post("/accounts", json={"name": "RevSender", "allow_overdraft": True})).json()
    a2 = (await client.post("/accounts", json={"name": "RevReceiver"})).json()

    t = (
        await client.post(
            "/transfers",
            json={"from_account_id": a1["id"], "to_account_id": a2["id"], "amount": 3000},
        )
    ).json()

    rev = await client.post(f"/transfers/{t['id']}/reverse")
    assert rev.status_code == 201

    alice = (await client.get(f"/accounts/{a1['id']}")).json()
    bob = (await client.get(f"/accounts/{a2['id']}")).json()
    assert alice["balance"] == 0
    assert bob["balance"] == 0


@pytest.mark.asyncio
async def test_double_reverse_rejected(client):
    a1 = (await client.post("/accounts", json={"name": "DblRevS", "allow_overdraft": True})).json()
    a2 = (await client.post("/accounts", json={"name": "DblRevR"})).json()

    t = (
        await client.post(
            "/transfers",
            json={"from_account_id": a1["id"], "to_account_id": a2["id"], "amount": 100},
        )
    ).json()

    assert (await client.post(f"/transfers/{t['id']}/reverse")).status_code == 201
    assert (await client.post(f"/transfers/{t['id']}/reverse")).status_code == 400


@pytest.mark.asyncio
async def test_get_entries(client):
    a1 = (await client.post("/accounts", json={"name": "EntryS", "allow_overdraft": True})).json()
    a2 = (await client.post("/accounts", json={"name": "EntryR"})).json()

    await client.post(
        "/transfers",
        json={"from_account_id": a1["id"], "to_account_id": a2["id"], "amount": 200},
    )
    entries = (await client.get(f"/accounts/{a1['id']}/entries")).json()
    assert len(entries) == 1
    assert entries[0]["entry_type"] == "debit"
    assert entries[0]["amount"] == 200
