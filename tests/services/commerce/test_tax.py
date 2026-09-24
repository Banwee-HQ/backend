"""Tests for services/commerce/tax.py - TaxService, the one tax lookup orders, subscriptions and the cart share.

make_tax_rate() flushes (not commits) - TaxService(db_session) queries through
the same session, so the row is visible within this test without needing a
commit, and the db_session fixture's rollback at teardown discards it
afterward. An earlier version of this file used real commits, which leaked
country_code rows across every CI run and eventually collided (2-char ISO
codes are a tiny namespace) - verified the isolation issue by reproducing a
false failure from exactly that leftover data before switching to flush().
"""

import pytest
from decimal import Decimal
import random
import string
from uuid import uuid4

from services.commerce.tax import TaxService
from models.commerce.tax_rates import TaxRate


def unique_code() -> str:
    # country_code is VARCHAR(2), so no UUID fragment - "X?" is ISO's user-assigned
    # range, never a real country, so it can't collide with seeded tax rates.
    return "X" + random.choice(string.ascii_uppercase)


async def make_tax_rate(db_session, country_code, tax_rate, country_name="Testland",
                         province_code=None, province_name=None, is_active=True) -> TaxRate:
    rate = TaxRate(
        id=uuid4(),
        country_code=country_code,
        country_name=country_name,
        province_code=province_code,
        province_name=province_name,
        tax_rate=tax_rate,
        is_active=is_active,
    )
    db_session.add(rate)
    await db_session.flush()
    return rate


class TestRateLookup:

    async def test_country_level_rate_by_code(self, db_session):
        code = unique_code()
        await make_tax_rate(db_session, country_code=code, tax_rate=0.10)
        assert await TaxService(db_session).rate(code) == pytest.approx(0.10)

    async def test_codes_and_names_are_case_insensitive(self, db_session):
        code = unique_code()
        name = f"Zedland-{code}"
        await make_tax_rate(db_session, country_code=code, country_name=name, tax_rate=0.07)
        service = TaxService(db_session)
        assert await service.rate(code.lower()) == pytest.approx(0.07)
        assert await service.rate(f"  {name.upper()} ") == pytest.approx(0.07)

    async def test_province_rate_wins_over_country_rate(self, db_session):
        code = unique_code()
        await make_tax_rate(db_session, country_code=code, tax_rate=0.05)
        await make_tax_rate(db_session, country_code=code, tax_rate=0.15, province_code="ZP", province_name="Zed Province")
        service = TaxService(db_session)
        assert await service.rate(code, "ZP") == pytest.approx(0.15)
        assert await service.rate(code, "zed province") == pytest.approx(0.15)

    async def test_address_as_stored_by_the_frontend(self, db_session):
        """Addresses hold full names ("Canada", "Ontario"); admin rates hold both codes and names."""
        name = f"Zedland-{unique_code()}"
        await make_tax_rate(db_session, country_code=unique_code(), country_name=name, tax_rate=0.13,
                            province_code="ZO", province_name="Zed Ontario")
        info = await TaxService(db_session).info(name, "Zed Ontario")
        assert info["tax_rate"] == pytest.approx(0.13)
        assert info["province_code"] == "ZO"

    async def test_unknown_province_falls_back_to_country_rate(self, db_session):
        code = unique_code()
        await make_tax_rate(db_session, country_code=code, tax_rate=0.03)
        info = await TaxService(db_session).info(code, "Nonexistent Province")
        assert info["tax_rate"] == pytest.approx(0.03)
        assert info["province_code"] is None

    async def test_other_provinces_rate_is_not_used(self, db_session):
        code = unique_code()
        await make_tax_rate(db_session, country_code=code, tax_rate=0.15, province_code="ZP")
        assert await TaxService(db_session).rate(code, "ZQ") == 0.0

    async def test_no_matching_rate_means_no_tax(self, db_session):
        service = TaxService(db_session)
        assert await service.rate(unique_code()) == 0.0
        assert await service.rate(None, None) == 0.0

    async def test_inactive_rate_is_not_used(self, db_session):
        code = unique_code()
        await make_tax_rate(db_session, country_code=code, tax_rate=0.99, is_active=False)
        assert await TaxService(db_session).rate(code) == 0.0

    async def test_rate_is_a_float_even_though_the_column_is_numeric(self, db_session):
        code = unique_code()
        await make_tax_rate(db_session, country_code=code, tax_rate=0.0725)
        assert isinstance(await TaxService(db_session).rate(code), float)


class TestAmount:

    def test_rounds_half_up_to_cents(self):
        assert TaxService.amount(Decimal("19.39"), 0.13) == Decimal("2.52")
        assert TaxService.amount(Decimal("0.50"), 0.05) == Decimal("0.03")

    def test_zero_rate_gives_zero_tax(self):
        assert TaxService.amount(Decimal("100"), 0.0) == Decimal("0.00")

    def test_negative_taxable_amount_is_never_taxed(self):
        assert TaxService.amount(Decimal("-5"), 0.13) == Decimal("0.00")
