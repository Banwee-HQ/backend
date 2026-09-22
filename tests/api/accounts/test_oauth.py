"""Tests for api/accounts/oauth.py - /v1/auth/social endpoints."""

import pytest
from uuid import uuid4
from httpx import AsyncClient, Response as HTTPXResponse

from api.accounts.oauth import get_user_info


@pytest.mark.api
@pytest.mark.auth
class TestOAuthEndpoints:

    async def test_google_missing_credential(self, async_client: AsyncClient):
        """POST /v1/auth/social/google - No credential is rejected."""
        response = await async_client.post("/v1/auth/social/google")
        assert response.status_code == 400

    async def test_google_invalid_credential(self, async_client: AsyncClient):
        """POST /v1/auth/social/google - Invalid credential fails verification."""
        response = await async_client.post("/v1/auth/social/google", params={"credential": "not-a-real-jwt"})
        assert response.status_code == 400

    async def test_facebook_missing_token(self, async_client: AsyncClient):
        """POST /v1/auth/social/facebook - No access token is rejected."""
        response = await async_client.post("/v1/auth/social/facebook")
        assert response.status_code == 400

    async def test_facebook_invalid_token(self, async_client: AsyncClient):
        """POST /v1/auth/social/facebook - Invalid access token fails verification."""
        response = await async_client.post("/v1/auth/social/facebook", params={"access_token": "not-a-real-token"})
        assert response.status_code == 400

    async def test_google_creates_new_user(self, async_client: AsyncClient, mocker):
        """Regression test: creating a new user via Google used to crash - the
        provider's avatar_url couldn't be set on the UserResponse auth_service.create()
        returns, and background_tasks=None broke the verification email send."""
        email = f"google_{uuid4().hex[:8]}@example.com"
        mocker.patch("api.accounts.oauth.verify_google_credential", return_value={
            "email": email, "name": "Ada Lovelace", "picture": "https://example.com/pic.jpg",
        })
        response = await async_client.post("/v1/auth/social/google", params={"credential": "fake-jwt"})
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["user"]["email"] == email
        assert data["user"]["verified"] is True
        assert data["user"]["avatar_url"] == "https://example.com/pic.jpg"
        assert "access_token" in data

    async def test_google_logs_in_existing_user(self, async_client: AsyncClient, mocker, test_user):
        """A known email logs in rather than creating a duplicate account."""
        mocker.patch("api.accounts.oauth.verify_google_credential", return_value={
            "email": test_user.email, "name": "Test User",
        })
        response = await async_client.post("/v1/auth/social/google", params={"credential": "fake-jwt"})
        assert response.status_code == 200
        assert response.json()["data"]["user"]["id"] == str(test_user.id)

    async def test_facebook_creates_new_user(self, async_client: AsyncClient, mocker):
        email = f"fb_{uuid4().hex[:8]}@example.com"
        mocker.patch("api.accounts.oauth.get_user_info", return_value={
            "id": "fb123", "email": email, "name": "Ada Lovelace",
        })
        response = await async_client.post("/v1/auth/social/facebook", params={"access_token": "fake-token"})
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["user"]["email"] == email
        assert data["user"]["avatar_url"] == "https://graph.facebook.com/fb123/picture?type=large"

    async def test_google_missing_email_is_rejected(self, async_client: AsyncClient, mocker):
        mocker.patch("api.accounts.oauth.verify_google_credential", return_value={"name": "No Email"})
        response = await async_client.post("/v1/auth/social/google", params={"credential": "fake-jwt"})
        assert response.status_code == 400

    async def test_facebook_missing_email_is_rejected(self, async_client: AsyncClient, mocker):
        """The facebook endpoint's HTTPException passthrough (as opposed to the generic
        exception fallback) - find_or_create_user() raises a plain HTTPException(400) when
        the provider gives no email, distinct from google's equivalent test above."""
        mocker.patch("api.accounts.oauth.get_user_info", return_value={"id": "fb1", "name": "No Email"})
        response = await async_client.post("/v1/auth/social/facebook", params={"access_token": "fake-token"})
        assert response.status_code == 400

    async def test_google_credential_with_invalid_email_hits_generic_exception(self, async_client: AsyncClient, mocker):
        """A provider that returns a syntactically invalid email causes a real pydantic
        ValidationError inside find_or_create_user()'s UserCreate(...) call, exercising the
        endpoint's generic `except Exception` fallback (not a mocked failure)."""
        mocker.patch("api.accounts.oauth.verify_google_credential", return_value={
            "email": "not-a-valid-email", "name": "Bad Email",
        })
        response = await async_client.post("/v1/auth/social/google", params={"credential": "fake-jwt"})
        assert response.status_code == 400
        assert "Google authentication failed" in str(response.json())

    async def test_verify_google_credential_success_path(self, async_client: AsyncClient, mocker):
        """Exercises the real verify_google_credential() function (not the usual test shortcut
        of mocking the wrapper itself) by mocking only the true external boundary: the
        google-auth library's own token-verification call."""
        mocker.patch("google.oauth2.id_token.verify_oauth2_token", return_value={
            "email": f"google_real_{uuid4().hex[:8]}@example.com",
            "name": "Grace Hopper",
            "picture": "https://example.com/grace.jpg",
        })
        response = await async_client.post("/v1/auth/social/google", params={"credential": "a-real-looking-jwt"})
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["user"]["email"].startswith("google_real_")
        assert data["user"]["avatar_url"] == "https://example.com/grace.jpg"

    async def test_google_logs_in_existing_user_updates_avatar(self, async_client: AsyncClient, mocker, test_user):
        """A known email with a picture updates the existing user's avatar_url (google branch
        of the existing-user update path in find_or_create_user)."""
        mocker.patch("api.accounts.oauth.verify_google_credential", return_value={
            "email": test_user.email, "name": "Test User", "picture": "https://example.com/updated.jpg",
        })
        response = await async_client.post("/v1/auth/social/google", params={"credential": "fake-jwt"})
        assert response.status_code == 200
        assert response.json()["data"]["user"]["avatar_url"] == "https://example.com/updated.jpg"

    async def test_facebook_logs_in_existing_user_updates_avatar(self, async_client: AsyncClient, mocker, test_user):
        """A known email logs in via facebook rather than creating a duplicate account, and
        the facebook branch of the existing-user avatar update runs."""
        mocker.patch("api.accounts.oauth.get_user_info", return_value={
            "id": "fb999", "email": test_user.email, "name": "Test User",
        })
        response = await async_client.post("/v1/auth/social/facebook", params={"access_token": "fake-token"})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["user"]["id"] == str(test_user.id)
        assert data["user"]["avatar_url"] == "https://graph.facebook.com/fb999/picture?type=large"


class TestGetUserInfoHelper:
    """Direct tests of get_user_info() - the only external dependency it has is the HTTP
    call itself, so only httpx is mocked; the function's own branching logic is real."""

    async def test_facebook_provider_builds_correct_params_and_parses_response(self, mocker):
        fake_response = mocker.Mock(spec=HTTPXResponse)
        fake_response.raise_for_status = mocker.Mock()
        fake_response.json = mocker.Mock(return_value={"id": "1", "name": "Ada", "email": "a@example.com"})
        mock_get = mocker.patch("httpx.AsyncClient.get", return_value=fake_response)

        result = await get_user_info("facebook", "some-token")

        assert result["email"] == "a@example.com"
        call_kwargs = mock_get.call_args.kwargs
        assert call_kwargs["params"]["access_token"] == "some-token"
        assert call_kwargs["params"]["fields"] == "id,name,email,picture"

    async def test_google_provider_builds_correct_params(self, mocker):
        """Covers the (currently unused-by-any-endpoint) google branch of get_user_info()."""
        fake_response = mocker.Mock(spec=HTTPXResponse)
        fake_response.raise_for_status = mocker.Mock()
        fake_response.json = mocker.Mock(return_value={"email": "a@example.com"})
        mock_get = mocker.patch("httpx.AsyncClient.get", return_value=fake_response)

        result = await get_user_info("google", "some-access-token")

        assert result["email"] == "a@example.com"
        assert mock_get.call_args.kwargs["params"] == {"access_token": "some-access-token"}
