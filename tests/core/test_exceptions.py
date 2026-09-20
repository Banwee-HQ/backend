"""Tests for core/exceptions.py - the custom exception hierarchy used across every endpoint."""

from core.exceptions import (
    format_error_response,
    APIException,
    ValidationException,
    AuthenticationException,
    AuthorizationException,
    NotFoundException,
    ConflictException,
    RateLimitException,
    DatabaseException,
    ExternalServiceException,
)


class TestFormatErrorResponse:

    def test_defaults(self):
        body = format_error_response("Something broke")
        assert body["success"] is False
        assert body["message"] == "Something broke"
        assert body["error_code"] == "ERR_500"
        assert "timestamp" in body

    def test_custom_status_derives_default_error_code(self):
        body = format_error_response("Not found", status_code=404)
        assert body["error_code"] == "ERR_404"

    def test_explicit_error_code_wins_over_default(self):
        body = format_error_response("Nope", status_code=404, error_code="CUSTOM")
        assert body["error_code"] == "CUSTOM"

    def test_extra_kwargs_are_merged_in(self):
        body = format_error_response("Bad input", errors={"field": "required"})
        assert body["errors"] == {"field": "required"}


class TestAPIException:

    def test_defaults_detail_to_message(self):
        exc = APIException(status_code=418)
        assert exc.detail == exc.message

    def test_explicit_detail_overrides_message_as_http_detail(self):
        exc = APIException(status_code=400, message="Public message", detail="Internal detail")
        assert exc.message == "Public message"
        assert exc.detail == "Internal detail"

    def test_error_code_defaults_from_status(self):
        exc = APIException(status_code=503)
        assert exc.error_code == "ERR_503"

    def test_is_a_real_http_exception(self):
        exc = APIException(status_code=400, message="Bad")
        assert exc.status_code == 400
        # FastAPI's exception handlers key off HTTPException.detail
        assert exc.detail == "Bad"

    def test_has_a_timestamp(self):
        exc = APIException(status_code=500)
        assert exc.timestamp  # non-empty ISO string


class TestExceptionSubclasses:
    """Each subclass should fix its status code/error code but still allow a custom message."""

    def test_validation_exception(self):
        exc = ValidationException(errors={"email": "invalid"})
        assert exc.status_code == 422
        assert exc.error_code == "VALIDATION_ERROR"
        assert exc.errors == {"email": "invalid"}

    def test_validation_exception_errors_default_to_empty_dict(self):
        assert ValidationException().errors == {}

    def test_authentication_exception(self):
        exc = AuthenticationException()
        assert exc.status_code == 401
        assert exc.error_code == "AUTH_ERROR"

    def test_authorization_exception(self):
        exc = AuthorizationException("Not your resource")
        assert exc.status_code == 403
        assert exc.message == "Not your resource"

    def test_not_found_exception_tracks_resource(self):
        exc = NotFoundException("Order not found", resource="order")
        assert exc.status_code == 404
        assert exc.resource == "order"

    def test_conflict_exception(self):
        assert ConflictException().status_code == 409

    def test_rate_limit_exception_tracks_retry_after(self):
        exc = RateLimitException(retry_after=30)
        assert exc.status_code == 429
        assert exc.retry_after == 30

    def test_database_exception(self):
        exc = DatabaseException()
        assert exc.status_code == 500
        assert exc.error_code == "DATABASE_ERROR"

    def test_external_service_exception_tracks_service_name(self):
        exc = ExternalServiceException(service="stripe")
        assert exc.status_code == 502
        assert exc.service == "stripe"

    def test_all_subclasses_are_api_exceptions(self):
        for exc in (
            ValidationException(), AuthenticationException(), AuthorizationException(),
            NotFoundException(), ConflictException(), RateLimitException(),
            DatabaseException(), ExternalServiceException(),
        ):
            assert isinstance(exc, APIException)
