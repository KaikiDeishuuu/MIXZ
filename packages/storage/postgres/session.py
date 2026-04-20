from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def get_postgres_dsn() -> str:
    dsn = os.getenv("MIXZ_POSTGRES_DSN")
    if not dsn:
        raise RuntimeError("MIXZ_POSTGRES_DSN is not set")
    return dsn


def create_engine_from_env(echo: bool = False):
    return create_engine(get_postgres_dsn(), future=True, pool_pre_ping=True, echo=echo)


def create_session_factory(engine=None) -> sessionmaker[Session]:
    target_engine = engine or create_engine_from_env()
    return sessionmaker(bind=target_engine, autoflush=False, autocommit=False, future=True)
