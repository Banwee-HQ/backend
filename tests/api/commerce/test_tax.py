"""Tests for api/commerce/tax.py - /v1/tax endpoints."""

import pytest
import random
import string
import itertools
from httpx import AsyncClient
from uuid import uuid4

# ISO's user-assigned range, never a real country - can't collide with seeded rates.
# Drawn without replacement so two codes issued in the same test/fixture can't collide by chance.
_USER_ASSIGNED_CODES = ["AA", "ZZ"] + [f"X{c}" for c in string.ascii_uppercase] + [f"Q{c}" for c in "MNOPQRSTUVWXYZ"]
random.shuffle(_USER_ASSIGNED_CODES)
_unique_code_pool = itertools.cycle(_USER_ASSIGNED_CODES)


def unique_code() -> str:
    return next(_unique_code_pool)


@pytest.fixture
async def created_rate(async_client: AsyncClient, admin_headers):
    """POST /rates/ uses response_model=RateResponse directly - no {data: ...} envelope."""
    response = await async_client.post("/v1/tax/rates/", headers=admin_headers, json={
        "country_code": unique_code(), "country_name": "Testland", "tax_rate": 0.0875, "tax_name": "Test Tax"
    })
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def created_rate_with_province(async_client: AsyncClient, admin_headers):
    """A rate with province fields set, for exercising province_code/province_name filters."""
    response = await async_client.post("/v1/tax/rates/", headers=admin_headers, json={
        "country_code": unique_code(), "country_name": "Provinceland",
        "province_code": "ZP", "province_name": "Zeta-Test Province",
        "tax_rate": 0.05, "tax_name": "Provincial Tax"
    })
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def inactive_rate(async_client: AsyncClient, admin_headers):
    response = await async_client.post("/v1/tax/rates/", headers=admin_headers, json={
        "country_code": unique_code(), "country_name": "Inactiveland", "tax_rate": 0.01, "is_active": False
    })
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def sortable_rates(async_client: AsyncClient, admin_headers):
    """Two rates that differ on every sortable field, scoped by a unique tag in their
    country_name so `?search=<tag>` isolates them from real seeded data and other tests."""
    tag = "".join(random.choices(string.ascii_lowercase, k=8))
    low = await async_client.post("/v1/tax/rates/", headers=admin_headers, json={
        "country_code": unique_code(), "country_name": f"Aland-{tag}", "tax_rate": 0.02, "tax_name": "Alpha Tax"
    })
    high = await async_client.post("/v1/tax/rates/", headers=admin_headers, json={
        "country_code": unique_code(), "country_name": f"Zland-{tag}", "tax_rate": 0.08, "tax_name": None
    })
    assert low.status_code == 201, low.text
    assert high.status_code == 201, high.text
    return tag, low.json(), high.json()


@pytest.mark.api
@pytest.mark.tax
class TestTaxRateEndpoints:

    async def test_list_as_admin(self, async_client: AsyncClient, admin_headers, created_rate):
        """GET /v1/tax/rates/ - Admin only; full rate configuration, not customer-facing."""
        response = await async_client.get("/v1/tax/rates/", headers=admin_headers)
        assert response.status_code == 200
        ids = [r["id"] for r in response.json()["data"]]
        assert created_rate["id"] in ids

    async def test_list_requires_admin(self, async_client: AsyncClient, auth_headers):
        response = await async_client.get("/v1/tax/rates/", headers=auth_headers)
        assert response.status_code == 403

    async def test_create(self, async_client: AsyncClient, created_rate):
        assert created_rate["country_name"] == "Testland"
        assert created_rate["tax_rate"] == 0.0875

    async def test_create_requires_admin(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post("/v1/tax/rates/", headers=auth_headers, json={
            "country_code": unique_code(), "country_name": "Testland", "tax_rate": 0.05
        })
        assert response.status_code == 403

    async def test_create_duplicate_is_rejected(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.post("/v1/tax/rates/", headers=admin_headers, json={
            "country_code": created_rate["country_code"], "country_name": "Testland", "tax_rate": 0.05
        })
        assert response.status_code == 400

    async def test_get_by_id(self, async_client: AsyncClient, admin_headers, created_rate):
        """GET /v1/tax/rates/{id} uses response_model=RateResponse directly - no envelope."""
        response = await async_client.get(f"/v1/tax/rates/{created_rate['id']}/", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["id"] == created_rate["id"]

    async def test_get_by_id_requires_admin(self, async_client: AsyncClient, auth_headers, created_rate):
        response = await async_client.get(f"/v1/tax/rates/{created_rate['id']}/", headers=auth_headers)
        assert response.status_code == 403

    async def test_get_unknown_id_returns_404(self, async_client: AsyncClient, admin_headers):
        response = await async_client.get(f"/v1/tax/rates/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_update(self, async_client: AsyncClient, admin_headers, created_rate):
        """PATCH /v1/tax/rates/{id} uses response_model=RateResponse directly - no envelope."""
        response = await async_client.patch(f"/v1/tax/rates/{created_rate['id']}/",
            headers=admin_headers, json={"tax_rate": 0.09})
        assert response.status_code == 200
        assert response.json()["tax_rate"] == 0.09

    async def test_update_unknown_id_returns_404(self, async_client: AsyncClient, admin_headers):
        response = await async_client.patch(f"/v1/tax/rates/{uuid4()}/",
            headers=admin_headers, json={"tax_rate": 0.09})
        assert response.status_code == 404

    async def test_delete(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.delete(f"/v1/tax/rates/{created_rate['id']}/", headers=admin_headers)
        assert response.status_code == 200

        get_after = await async_client.get(f"/v1/tax/rates/{created_rate['id']}/", headers=admin_headers)
        assert get_after.status_code == 404

    async def test_delete_unknown_id_returns_404(self, async_client: AsyncClient, admin_headers):
        response = await async_client.delete(f"/v1/tax/rates/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404


    async def test_list_filters_by_country_code(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.get(f"/v1/tax/rates/?country_code={created_rate['country_code']}", headers=admin_headers)
        assert response.status_code == 200
        assert all(r["country_code"] == created_rate["country_code"] for r in response.json()["data"])

    async def test_list_filters_by_search(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.get("/v1/tax/rates/?search=Testland", headers=admin_headers)
        assert response.status_code == 200
        ids = [r["id"] for r in response.json()["data"]]
        assert created_rate["id"] in ids

    async def test_list_sort_by_tax_rate(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.get("/v1/tax/rates/?sort_by=tax_rate&sort_order=asc", headers=admin_headers)
        assert response.status_code == 200

    async def test_bulk_update(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.post("/v1/tax/rates/bulk-update/", headers=admin_headers, json=[
            {"id": created_rate["id"], "tax_rate": 0.1}
        ])
        assert response.status_code == 200
        assert response.json()["data"]["updated_count"] == 1

    async def test_bulk_update_reports_unknown_id(self, async_client: AsyncClient, admin_headers):
        response = await async_client.post("/v1/tax/rates/bulk-update/", headers=admin_headers, json=[
            {"id": str(uuid4()), "tax_rate": 0.1}
        ])
        assert response.status_code == 404  # all-or-nothing: nothing is changed

    async def test_bulk_update_rejects_out_of_range_rates(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.post("/v1/tax/rates/bulk-update/", headers=admin_headers, json=[
            {"id": created_rate["id"], "tax_rate": 5}
        ])
        assert response.status_code == 422

    async def test_bulk_update_requires_admin(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post("/v1/tax/rates/bulk-update/", headers=auth_headers, json=[])
        assert response.status_code == 403


@pytest.mark.api
@pytest.mark.tax
class TestListRatesFilters:
    """Filters not covered by test_list_filters_by_country_code / by_search above."""

    async def test_filter_by_country_name(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.get("/v1/tax/rates/?country_name=Testland", headers=admin_headers)
        assert response.status_code == 200
        ids = [r["id"] for r in response.json()["data"]]
        assert created_rate["id"] in ids

    async def test_filter_by_province_code(self, async_client: AsyncClient, admin_headers, created_rate_with_province):
        response = await async_client.get(
            f"/v1/tax/rates/?province_code={created_rate_with_province['province_code']}", headers=admin_headers
        )
        assert response.status_code == 200
        ids = [r["id"] for r in response.json()["data"]]
        assert created_rate_with_province["id"] in ids

    async def test_filter_by_province_name(self, async_client: AsyncClient, admin_headers, created_rate_with_province):
        response = await async_client.get("/v1/tax/rates/?province_name=Zeta-Test", headers=admin_headers)
        assert response.status_code == 200
        ids = [r["id"] for r in response.json()["data"]]
        assert created_rate_with_province["id"] in ids

    async def test_filter_by_is_active_true_excludes_inactive(
        self, async_client: AsyncClient, admin_headers, created_rate, inactive_rate
    ):
        response = await async_client.get("/v1/tax/rates/?is_active=true", headers=admin_headers)
        assert response.status_code == 200
        ids = [r["id"] for r in response.json()["data"]]
        assert created_rate["id"] in ids
        assert inactive_rate["id"] not in ids

    async def test_filter_by_is_active_false_only_returns_inactive(
        self, async_client: AsyncClient, admin_headers, created_rate, inactive_rate
    ):
        response = await async_client.get("/v1/tax/rates/?is_active=false", headers=admin_headers)
        assert response.status_code == 200
        ids = [r["id"] for r in response.json()["data"]]
        assert inactive_rate["id"] in ids
        assert created_rate["id"] not in ids


@pytest.mark.api
@pytest.mark.tax
class TestListRatesSorting:
    """Each branch of the sort_by/sort_order dispatch, verified against actual order -
    not just a 200 status - using two rates scoped by a unique search tag so real
    seeded rows in the shared dev DB can't interfere with the ordering assertions."""

    async def test_sort_by_created_at_asc(self, async_client: AsyncClient, admin_headers, sortable_rates):
        tag, low, high = sortable_rates  # low created first
        response = await async_client.get(f"/v1/tax/rates/?search={tag}&sort_by=created_at&sort_order=asc", headers=admin_headers)
        assert response.status_code == 200
        ids = [r["id"] for r in response.json()["data"]]
        assert ids.index(low["id"]) < ids.index(high["id"])

    async def test_sort_by_country_name_asc(self, async_client: AsyncClient, admin_headers, sortable_rates):
        tag, low, high = sortable_rates  # "Aland-..." < "Zland-..."
        response = await async_client.get(f"/v1/tax/rates/?search={tag}&sort_by=country_name&sort_order=asc", headers=admin_headers)
        assert response.status_code == 200
        names = [r["country_name"] for r in response.json()["data"]]
        assert names.index(low["country_name"]) < names.index(high["country_name"])

    async def test_sort_by_country_name_desc(self, async_client: AsyncClient, admin_headers, sortable_rates):
        tag, low, high = sortable_rates
        response = await async_client.get(f"/v1/tax/rates/?search={tag}&sort_by=country_name&sort_order=desc", headers=admin_headers)
        assert response.status_code == 200
        names = [r["country_name"] for r in response.json()["data"]]
        assert names.index(high["country_name"]) < names.index(low["country_name"])

    async def test_sort_by_tax_rate_desc(self, async_client: AsyncClient, admin_headers, sortable_rates):
        tag, low, high = sortable_rates  # low=0.02, high=0.08
        response = await async_client.get(f"/v1/tax/rates/?search={tag}&sort_by=tax_rate&sort_order=desc", headers=admin_headers)
        assert response.status_code == 200
        ids = [r["id"] for r in response.json()["data"]]
        assert ids.index(high["id"]) < ids.index(low["id"])

    async def test_sort_by_tax_name_asc_nulls_last(self, async_client: AsyncClient, admin_headers, sortable_rates):
        tag, low, high = sortable_rates  # low has "Alpha Tax", high has tax_name=None
        response = await async_client.get(f"/v1/tax/rates/?search={tag}&sort_by=tax_name&sort_order=asc", headers=admin_headers)
        assert response.status_code == 200
        ids = [r["id"] for r in response.json()["data"]]
        assert ids.index(low["id"]) < ids.index(high["id"])

    async def test_sort_by_tax_name_desc_nulls_last(self, async_client: AsyncClient, admin_headers, sortable_rates):
        tag, low, high = sortable_rates
        response = await async_client.get(f"/v1/tax/rates/?search={tag}&sort_by=tax_name&sort_order=desc", headers=admin_headers)
        assert response.status_code == 200
        ids = [r["id"] for r in response.json()["data"]]
        # nulls_last() applies in both asc and desc, so the null (high) still sorts after low.
        assert ids.index(low["id"]) < ids.index(high["id"])

    async def test_sort_by_unknown_field_uses_default(self, async_client: AsyncClient, admin_headers, sortable_rates):
        tag, low, high = sortable_rates
        response = await async_client.get(f"/v1/tax/rates/?search={tag}&sort_by=totally_bogus_field", headers=admin_headers)
        assert response.status_code == 200
        names = [r["country_name"] for r in response.json()["data"]]
        # Default sort is (country_name, province_name) ascending.
        assert names.index(low["country_name"]) < names.index(high["country_name"])


@pytest.mark.api
@pytest.mark.tax
class TestListRatesErrors:

    async def test_list_rates_error_returns_500(self, async_client: AsyncClient, admin_headers, monkeypatch):
        import api.commerce.tax as tax_api
        monkeypatch.setattr(
            tax_api.Response, "success",
            staticmethod(lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        )
        response = await async_client.get("/v1/tax/rates/", headers=admin_headers)
        assert response.status_code == 500
        assert "Failed to fetch tax rates" in response.json()["message"]


@pytest.mark.api
@pytest.mark.tax
class TestGetRateErrors:

    async def test_get_rate_generic_exception_returns_500(
        self, async_client: AsyncClient, admin_headers, created_rate, monkeypatch
    ):
        import api.commerce.tax as tax_api
        monkeypatch.setattr(
            tax_api, "RateResponse",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        response = await async_client.get(f"/v1/tax/rates/{created_rate['id']}/", headers=admin_headers)
        assert response.status_code == 500
        assert "Failed to get tax rate" in response.json()["message"]


@pytest.mark.api
@pytest.mark.tax
class TestCreateRateErrors:

    async def test_create_rate_generic_exception_returns_500(
        self, async_client: AsyncClient, admin_headers, monkeypatch
    ):
        import api.commerce.tax as tax_api
        monkeypatch.setattr(
            tax_api, "RateResponse",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        response = await async_client.post("/v1/tax/rates/", headers=admin_headers, json={
            "country_code": unique_code(), "country_name": "Boomland", "tax_rate": 0.05
        })
        assert response.status_code == 500
        assert "Failed to create tax rate" in response.json()["message"]


@pytest.mark.api
@pytest.mark.tax
class TestUpdateRateFields:
    """Each independently-optional field on RateUpdate, beyond the tax_rate-only
    update already covered by TestTaxRateEndpoints.test_update."""

    async def test_update_country_name(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.patch(
            f"/v1/tax/rates/{created_rate['id']}/", headers=admin_headers, json={"country_name": "Renamedland"}
        )
        assert response.status_code == 200
        assert response.json()["country_name"] == "Renamedland"

    async def test_update_province_name(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.patch(
            f"/v1/tax/rates/{created_rate['id']}/", headers=admin_headers, json={"province_name": "New Province"}
        )
        assert response.status_code == 200
        assert response.json()["province_name"] == "New Province"

    async def test_update_tax_name(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.patch(
            f"/v1/tax/rates/{created_rate['id']}/", headers=admin_headers, json={"tax_name": "Renamed Tax"}
        )
        assert response.status_code == 200
        assert response.json()["tax_name"] == "Renamed Tax"

    async def test_update_is_active(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.patch(
            f"/v1/tax/rates/{created_rate['id']}/", headers=admin_headers, json={"is_active": False}
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

        # Re-fetch independently to make sure the mutation was actually persisted,
        # not just reflected in the same in-memory object returned by the PATCH.
        get_after = await async_client.get(f"/v1/tax/rates/{created_rate['id']}/", headers=admin_headers)
        assert get_after.json()["is_active"] is False


@pytest.mark.api
@pytest.mark.tax
class TestUpdateRateErrors:

    async def test_update_rate_generic_exception_returns_500(
        self, async_client: AsyncClient, admin_headers, created_rate, monkeypatch
    ):
        import api.commerce.tax as tax_api
        monkeypatch.setattr(
            tax_api, "RateResponse",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        response = await async_client.patch(
            f"/v1/tax/rates/{created_rate['id']}/", headers=admin_headers, json={"tax_rate": 0.2}
        )
        assert response.status_code == 500
        assert "Failed to update tax rate" in response.json()["message"]


@pytest.mark.api
@pytest.mark.tax
class TestDeleteRateErrors:

    async def test_delete_rate_generic_exception_returns_500(
        self, async_client: AsyncClient, admin_headers, created_rate, monkeypatch
    ):
        import api.commerce.tax as tax_api
        monkeypatch.setattr(
            tax_api.Response, "success",
            staticmethod(lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        )
        response = await async_client.delete(f"/v1/tax/rates/{created_rate['id']}/", headers=admin_headers)
        assert response.status_code == 500
        assert "Failed to delete tax rate" in response.json()["message"]


@pytest.mark.api
@pytest.mark.tax
class TestTaxPublicLists:

    async def test_countries_list(self, async_client: AsyncClient):
        response = await async_client.get("/v1/tax/countries/")
        assert response.status_code == 200

    async def test_tax_types_list(self, async_client: AsyncClient):
        response = await async_client.get("/v1/tax/tax-types/")
        assert response.status_code == 200


@pytest.mark.api
@pytest.mark.tax
class TestCountriesEndpoint:

    async def test_countries_includes_created_rate(self, async_client: AsyncClient, created_rate):
        response = await async_client.get("/v1/tax/countries/")
        assert response.status_code == 200
        codes = [c["country_code"] for c in response.json()["data"]]
        assert created_rate["country_code"] in codes

    async def test_countries_error_returns_500(self, async_client: AsyncClient, monkeypatch):
        import api.commerce.tax as tax_api
        monkeypatch.setattr(
            tax_api.Response, "success",
            staticmethod(lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        )
        response = await async_client.get("/v1/tax/countries/")
        assert response.status_code == 500
        assert "Failed to fetch countries" in response.json()["message"]


@pytest.mark.api
@pytest.mark.tax
class TestTaxTypesEndpoint:

    async def test_tax_types_includes_created_rate(self, async_client: AsyncClient, created_rate):
        response = await async_client.get("/v1/tax/tax-types/")
        assert response.status_code == 200
        names = [t["value"] for t in response.json()["data"]]
        assert created_rate["tax_name"] in names

    async def test_tax_types_error_returns_500(self, async_client: AsyncClient, monkeypatch):
        import api.commerce.tax as tax_api
        monkeypatch.setattr(
            tax_api.Response, "success",
            staticmethod(lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        )
        response = await async_client.get("/v1/tax/tax-types/")
        assert response.status_code == 500
        assert "Failed to fetch tax types" in response.json()["message"]


@pytest.mark.api
@pytest.mark.tax
class TestBulkUpdateFields:

    async def test_bulk_update_is_active(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.post("/v1/tax/rates/bulk-update/", headers=admin_headers, json=[
            {"id": created_rate["id"], "is_active": False}
        ])
        assert response.status_code == 200
        assert response.json()["data"]["updated_count"] == 1

        get_after = await async_client.get(f"/v1/tax/rates/{created_rate['id']}/", headers=admin_headers)
        assert get_after.json()["is_active"] is False

    async def test_bulk_update_tax_name(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.post("/v1/tax/rates/bulk-update/", headers=admin_headers, json=[
            {"id": created_rate["id"], "tax_name": "Bulk Renamed"}
        ])
        assert response.status_code == 200
        assert response.json()["data"]["updated_count"] == 1

        get_after = await async_client.get(f"/v1/tax/rates/{created_rate['id']}/", headers=admin_headers)
        assert get_after.json()["tax_name"] == "Bulk Renamed"


@pytest.mark.api
@pytest.mark.tax
class TestBulkUpdateValidation:

    @pytest.mark.parametrize("item", [{"id": "not-a-uuid", "is_active": False}, {"is_active": False}])
    async def test_bad_items_are_rejected_before_anything_changes(self, async_client: AsyncClient, admin_headers, item):
        response = await async_client.post("/v1/tax/rates/bulk-update/", headers=admin_headers, json=[item])
        assert response.status_code == 422