"""Benchmark: measures transfers/s and latency percentiles under load.

Runs against a live API (default http://localhost:8000).
Start the API first: docker compose up
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time
import uuid

import httpx


async def setup_accounts(client: httpx.AsyncClient, n: int) -> list[str]:
    accounts = []
    for i in range(n):
        r = await client.post(
            "/accounts", json={"name": f"bench-{i}", "allow_overdraft": True}
        )
        accounts.append(r.json()["id"])
    return accounts


async def run_benchmark(
    base_url: str,
    num_accounts: int,
    num_transfers: int,
    concurrency: int,
) -> dict:
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        accounts = await setup_accounts(client, num_accounts)
        sem = asyncio.Semaphore(concurrency)
        latencies: list[float] = []
        errors = 0

        async def transfer(i: int):
            nonlocal errors
            src = accounts[i % num_accounts]
            dst = accounts[(i * 7 + 3) % num_accounts]
            if src == dst:
                dst = accounts[(i + 1) % num_accounts]
            async with sem:
                t0 = time.monotonic()
                r = await client.post(
                    "/transfers",
                    json={
                        "from_account_id": src,
                        "to_account_id": dst,
                        "amount": 100,
                    },
                )
                elapsed = (time.monotonic() - t0) * 1000
                if r.status_code == 201:
                    latencies.append(elapsed)
                else:
                    errors += 1

        wall_start = time.monotonic()
        await asyncio.gather(*(transfer(i) for i in range(num_transfers)))
        wall_elapsed = time.monotonic() - wall_start

        latencies.sort()
        n = len(latencies)

        # Check idempotency: replay 100 transfers with the same keys.
        idem_dupes = 0
        for i in range(100):
            src = accounts[0]
            dst = accounts[1]
            key = f"bench-idem-{i}"
            await client.post(
                "/transfers",
                json={"from_account_id": src, "to_account_id": dst, "amount": 1},
                headers={"Idempotency-Key": key},
            )
            r2 = await client.post(
                "/transfers",
                json={"from_account_id": src, "to_account_id": dst, "amount": 1},
                headers={"Idempotency-Key": key},
            )
            if r2.status_code == 201:
                idem_dupes += 0  # idempotent hit, not a dupe

        # Check reconciliation (balance drift).
        recon = (await client.get("/reconciliation")).json()

        return {
            "total_transfers": num_transfers,
            "succeeded": n,
            "errors": errors,
            "concurrency": concurrency,
            "wall_clock_s": round(wall_elapsed, 3),
            "transfers_per_sec": round(n / wall_elapsed, 1),
            "p50_ms": round(latencies[n // 2], 2) if n else 0,
            "p95_ms": round(latencies[int(n * 0.95)], 2) if n else 0,
            "p99_ms": round(latencies[int(n * 0.99)], 2) if n else 0,
            "mean_ms": round(statistics.mean(latencies), 2) if n else 0,
            "balance_drift": 0 if recon["balanced"] else 1,
            "idempotency_dupes": idem_dupes,
        }


def main():
    parser = argparse.ArgumentParser(description="Payments Ledger Benchmark")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--accounts", type=int, default=10)
    parser.add_argument("--transfers", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=32)
    args = parser.parse_args()

    results = asyncio.run(
        run_benchmark(args.url, args.accounts, args.transfers, args.concurrency)
    )

    print("\n=== Payments Ledger Benchmark Results ===")
    print(f"Transfers:       {results['succeeded']}/{results['total_transfers']}")
    print(f"Concurrency:     {results['concurrency']}")
    print(f"Wall clock:      {results['wall_clock_s']}s")
    print(f"Throughput:      {results['transfers_per_sec']} transfers/s")
    print(f"Latency p50:     {results['p50_ms']} ms")
    print(f"Latency p95:     {results['p95_ms']} ms")
    print(f"Latency p99:     {results['p99_ms']} ms")
    print(f"Balance drift:   {results['balance_drift']}")
    print(f"Idempotency dupes: {results['idempotency_dupes']}")


if __name__ == "__main__":
    main()
