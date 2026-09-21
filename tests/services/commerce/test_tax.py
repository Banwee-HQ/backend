"""Tests for services/commerce/tax.py - TaxService.

calculate_tax previously crashed with 'unsupported operand type(s) for *:
float and decimal.Decimal' whenever rate() resolved a tax rate from the DB
(a Decimal column) instead of the all-lookups-missed fallback (a float
literal) - these tests exercise the exact real-DB path that triggered it,
not just the fallback.

make_tax_rate() flushes (not commits) - TaxService(db_session) queries through
the same session, so the row is visible within this test without needing a
commit, and the db_session fixture's rollback at teardown discards it
afterward. An earlier version of this file used real commits, which leaked
country_code rows across every CI run and eventually collided (2-char ISO
codes are a tiny namespace) - verified the isolation issue by reproducing a
false failure from exactly that leftover data before switching to flush().
"""

import pytest
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


class TestRateLookupByCode:

    async def test_country_level_rate_by_code(self, db_session):
        code = unique_code()
        await make_tax_rate(db_session, country_code=code, tax_rate=0.10)
        service = TaxService(db_session)
        rate = await service.rate(country_code=code)
        assert float(rate) == pytest.approx(0.10)

    async def test_province_level_rate_takes_priority_over_country_level(self, db_session):
        code = unique_code()
        await make_tax_rate(db_session, country_code=code, tax_rate=0.05)
        await make_tax_rate(db_session, country_code=code, tax_rate=0.15, province_code="ZP")
        service = TaxService(db_session)
        rate = await service.rate(country_code=code, province_code="ZP")
        assert float(rate) == pytest.approx(0.15)

    async def test_no_matching_rate_falls_back_to_zero(self, db_session):
        service = TaxService(db_session)
        rate = await service.rate(country_code=unique_code())
        assert float(rate) == 0.0

    async def test_inactive_rate_is_not_used(self, db_session):
        code = unique_code()
        await make_tax_rate(db_session, country_code=code, tax_rate=0.99, is_active=False)
        service = TaxService(db_session)
        rate = await service.rate(country_code=code)
        assert float(rate) == 0.0


class TestRateLookupByName:
    """calc_pricing() in orders.py calls rate() with only country_name/province_name -
    no country_code at all - this must not crash (that was the None.upper() bug)."""

    async def test_lookup_by_country_and_province_name_with_no_codes_at_all(self, db_session):
        name = f"Zedland-{unique_code()}"
        await make_tax_rate(db_session, country_code=unique_code(), country_name=name,
                             tax_rate=0.08, province_name="Zed Province")
        service = TaxService(db_session)
        rate = await service.rate(country_code=None, province_code=None,
                                   country_name=name, province_name="Zed Province")
        assert float(rate) == pytest.approx(0.08)

    async def test_lookup_by_country_name_only_with_no_codes_at_all(self, db_session):
        name = f"Zedland-{unique_code()}"
        await make_tax_rate(db_session, country_code=unique_code(), country_name=name, tax_rate=0.07)
        service = TaxService(db_session)
        rate = await service.rate(country_code=None, province_code=None, country_name=name)
        assert float(rate) == pytest.approx(0.07)

    async def test_unmatched_name_with_no_codes_returns_zero_without_raising(self, db_session):
        """This is the exact regression: country_code=None used to hit .upper() and crash."""
        service = TaxService(db_session)
        rate = await service.rate(country_code=None, province_code=None,
                                   country_name=f"Nowhereland-{unique_code()}",
                                   province_name="Nowhere Province")
        assert float(rate) == 0.0


class TestCalculateTax:

    async def test_calculates_tax_from_a_real_decimal_db_rate(self, db_session):
        """The actual regression: DB tax_rate is a Decimal, amount is a float."""
        code = unique_code()
        await make_tax_rate(db_session, country_code=code, tax_rate=0.10)
        service = TaxService(db_session)
        tax_amount = await service.calculate_tax(100.0, country_code=code)
        assert tax_amount == pytest.approx(10.0)

    async def test_zero_rate_gives_zero_tax(self, db_session):
        service = TaxService(db_session)
        tax_amount = await service.calculate_tax(100.0, country_code=unique_code())
        assert tax_amount == 0.0

    async def test_result_is_rounded_to_cents(self, db_session):
        code = unique_code()
        await make_tax_rate(db_session, country_code=code, tax_rate=0.0725)
        service = TaxService(db_session)
        tax_amount = await service.calculate_tax(19.99, country_code=code)
        assert round(tax_amount, 2) == tax_amount
