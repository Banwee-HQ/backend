"""Tests for schemas/system/response.py - generic APIResponse."""

from schemas.system.response import APIResponse


class TestAPIResponse:

    def test_wraps_arbitrary_data_payload(self):
        response = APIResponse[dict](success=True, message="ok", data={"id": 1}, pagination=None)
        assert response.data == {"id": 1}

    def test_allows_none_data(self):
        response = APIResponse[dict](success=False, message="not found", data=None, pagination=None)
        assert response.data is None
