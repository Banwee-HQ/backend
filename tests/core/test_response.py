"""Tests for core/utils/response.py - the standardized JSONResponse wrapper every endpoint returns."""

import json
from datetime import datetime, date
from decimal import Decimal
from uuid import uuid4

from pydantic import BaseModel

from core.utils.response import Response


def body_of(response: Response) -> dict:
    return json.loads(response.body)


class TestResponseSuccess:

    def test_default_shape(self):
        response = Response.success()
        body = body_of(response)
        assert body == {"success": True, "data": None, "message": "Success"}
        assert response.status_code == 200

    def test_carries_data_through(self):
        response = Response.success(data={"id": 1})
        assert body_of(response)["data"] == {"id": 1}

    def test_custom_message_and_status(self):
        response = Response.success(message="Created", status_code=201)
        body = body_of(response)
        assert body["message"] == "Created"
        assert response.status_code == 201

    def test_pagination_included_only_when_given(self):
        without = body_of(Response.success())
        assert "pagination" not in without

        with_pagination = body_of(Response.success(pagination={"page": 1, "total": 10}))
        assert with_pagination["pagination"] == {"page": 1, "total": 10}


class TestResponseError:

    def test_default_shape(self):
        response = Response.error()
        body = body_of(response)
        assert body["success"] is False
        assert response.status_code == 400

    def test_custom_message_and_status(self):
        response = Response.error(message="Not found", status_code=404)
        body = body_of(response)
        assert body["message"] == "Not found"
        assert response.status_code == 404

    def test_errors_list_included_only_when_given(self):
        without = body_of(Response.error())
        assert "errors" not in without

        with_errors = body_of(Response.error(errors=[{"field": "email", "message": "required"}]))
        assert with_errors["errors"] == [{"field": "email", "message": "required"}]


class TestDataSerialization:
    """Response._serialize_data has to cope with everything a service might hand back raw."""

    def test_serializes_uuid_to_string(self):
        value = uuid4()
        body = body_of(Response.success(data={"id": value}))
        assert body["data"]["id"] == str(value)

    def test_serializes_datetime_to_isoformat(self):
        now = datetime(2026, 1, 1, 12, 30, 0)
        body = body_of(Response.success(data={"created_at": now}))
        assert body["data"]["created_at"] == now.isoformat()

    def test_serializes_date_to_isoformat(self):
        today = date(2026, 1, 1)
        body = body_of(Response.success(data={"day": today}))
        assert body["data"]["day"] == today.isoformat()

    def test_serializes_decimal_to_float(self):
        body = body_of(Response.success(data={"price": Decimal("19.99")}))
        assert body["data"]["price"] == 19.99

    def test_serializes_pydantic_model(self):
        class Item(BaseModel):
            name: str
            price: float

        body = body_of(Response.success(data=Item(name="Widget", price=9.99)))
        assert body["data"] == {"name": "Widget", "price": 9.99}

    def test_serializes_list_of_mixed_items(self):
        value = uuid4()
        body = body_of(Response.success(data=[value, Decimal("1.50"), "plain"]))
        assert body["data"] == [str(value), 1.50, "plain"]

    def test_serializes_nested_dict_values(self):
        value = uuid4()
        body = body_of(Response.success(data={"outer": {"id": value}}))
        assert body["data"]["outer"]["id"] == str(value)

    def test_none_data_stays_none(self):
        assert body_of(Response.success(data=None))["data"] is None

    def test_plain_json_types_pass_through_unchanged(self):
        body = body_of(Response.success(data={"a": 1, "b": "two", "c": True, "d": None}))
        assert body["data"] == {"a": 1, "b": "two", "c": True, "d": None}
