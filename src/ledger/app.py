from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from ledger.database import engine
from ledger.models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Payments Ledger API", version="0.1.0", lifespan=lifespan)

    from ledger.api.accounts import router as accounts_router
    from ledger.api.health import router as health_router
    from ledger.api.reconciliation import router as reconciliation_router
    from ledger.api.transfers import router as transfers_router

    app.include_router(health_router)
    app.include_router(accounts_router)
    app.include_router(transfers_router)
    app.include_router(reconciliation_router)
    return app


app = create_app()
