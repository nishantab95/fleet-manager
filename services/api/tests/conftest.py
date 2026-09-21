from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from fleet_api.core.config import Settings
from fleet_api.db.models import (
    Company,
    CompanyMembership,
    Site,
    Tipper,
    User,
)
from fleet_api.domain.enums import (
    CompanyStatus,
    MembershipRole,
    MembershipStatus,
    SiteStatus,
    TipperStatus,
    UserStatus,
)


@pytest.fixture(scope="session")
def postgres_engine() -> Iterator[Engine]:
    database_url = os.getenv("FLEET_TEST_DATABASE_URL")
    if not database_url:
        application_url = make_url(Settings().database_url)
        database_url = str(
            application_url.set(database=f"{application_url.database or 'fleet'}_test")
        )
    database_name = make_url(database_url).database or ""
    if "test" not in database_name.lower():
        raise AssertionError("FLEET_TEST_DATABASE_URL must point to a database named for testing")
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")

    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_config, "head")
    yield engine
    command.downgrade(alembic_config, "base")
    engine.dispose()


@pytest.fixture
def db_session(postgres_engine: Engine) -> Iterator[Session]:
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def tenant_records(db_session: Session) -> dict[str, object]:
    company_a = Company(name="Alpha Construction", status=CompanyStatus.ACTIVE)
    company_b = Company(name="Beta Construction", status=CompanyStatus.ACTIVE)
    users = {
        "driver_a": User(
            phone_number=f"+9100000{uuid4().int % 100000:05d}",
            display_name="Driver A",
            status=UserStatus.ACTIVE,
        ),
        "driver_a2": User(
            phone_number=f"+9100001{uuid4().int % 100000:05d}",
            display_name="Driver A2",
            status=UserStatus.ACTIVE,
        ),
        "supervisor_a": User(
            phone_number=f"+9200000{uuid4().int % 100000:05d}",
            display_name="Supervisor A",
            status=UserStatus.ACTIVE,
        ),
        "owner_a": User(
            phone_number=f"+9300000{uuid4().int % 100000:05d}",
            display_name="Owner A",
            status=UserStatus.ACTIVE,
        ),
        "driver_b": User(
            phone_number=f"+9400000{uuid4().int % 100000:05d}",
            display_name="Driver B",
            status=UserStatus.ACTIVE,
        ),
        "supervisor_b": User(
            phone_number=f"+9500000{uuid4().int % 100000:05d}",
            display_name="Supervisor B",
            status=UserStatus.ACTIVE,
        ),
    }
    db_session.add_all([company_a, company_b, *users.values()])
    db_session.flush()
    memberships = {
        "driver_a": CompanyMembership(
            company_id=company_a.id,
            user_id=users["driver_a"].id,
            role=MembershipRole.DRIVER,
            status=MembershipStatus.ACTIVE,
        ),
        "driver_a2": CompanyMembership(
            company_id=company_a.id,
            user_id=users["driver_a2"].id,
            role=MembershipRole.DRIVER,
            status=MembershipStatus.ACTIVE,
        ),
        "supervisor_a": CompanyMembership(
            company_id=company_a.id,
            user_id=users["supervisor_a"].id,
            role=MembershipRole.SUPERVISOR,
            status=MembershipStatus.ACTIVE,
        ),
        "owner_a": CompanyMembership(
            company_id=company_a.id,
            user_id=users["owner_a"].id,
            role=MembershipRole.OWNER_ADMIN,
            status=MembershipStatus.ACTIVE,
        ),
        "driver_b": CompanyMembership(
            company_id=company_b.id,
            user_id=users["driver_b"].id,
            role=MembershipRole.DRIVER,
            status=MembershipStatus.ACTIVE,
        ),
        "supervisor_b": CompanyMembership(
            company_id=company_b.id,
            user_id=users["supervisor_b"].id,
            role=MembershipRole.SUPERVISOR,
            status=MembershipStatus.ACTIVE,
        ),
    }
    db_session.add_all(memberships.values())
    site_a = Site(
        company_id=company_a.id,
        name="Alpha Site",
        code="ALPHA",
        status=SiteStatus.ACTIVE,
    )
    site_b = Site(
        company_id=company_b.id,
        name="Beta Site",
        code="BETA",
        status=SiteStatus.ACTIVE,
    )
    tipper_a = Tipper(
        company_id=company_a.id,
        registration_number="KA01AB1234",
        short_name="Alpha One",
        status=TipperStatus.ACTIVE,
    )
    tipper_b = Tipper(
        company_id=company_b.id,
        registration_number="KA02BC5678",
        short_name="Beta One",
        status=TipperStatus.ACTIVE,
    )
    db_session.add_all([site_a, site_b, tipper_a, tipper_b])
    db_session.flush()
    return {
        "company_a": company_a,
        "company_b": company_b,
        "site_a": site_a,
        "site_b": site_b,
        "tipper_a": tipper_a,
        "tipper_b": tipper_b,
        **users,
        **memberships,
    }
