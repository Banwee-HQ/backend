"""Tests for core/utils/encryption.py - password hashing."""

import pytest

from core.utils.encryption import PasswordManager, hash_password, verify_password


@pytest.fixture
def manager():
    return PasswordManager()


class TestPasswordHashing:

    def test_hash_is_not_the_plaintext(self, manager):
        hashed = manager.hash_password("correct horse battery staple")
        assert hashed != "correct horse battery staple"

    def test_hash_uses_argon2(self, manager):
        hashed = manager.hash_password("whatever")
        assert hashed.startswith("$argon2")

    def test_same_password_hashes_differently_each_time(self, manager):
        """Argon2 salts each hash, so two hashes of the same password must differ."""
        a = manager.hash_password("same-password")
        b = manager.hash_password("same-password")
        assert a != b

    def test_verify_accepts_the_correct_password(self, manager):
        hashed = manager.hash_password("my-real-password")
        assert manager.verify_password("my-real-password", hashed) is True

    def test_verify_rejects_the_wrong_password(self, manager):
        hashed = manager.hash_password("my-real-password")
        assert manager.verify_password("not-my-password", hashed) is False

    def test_verify_is_case_sensitive(self, manager):
        hashed = manager.hash_password("Sensitive")
        assert manager.verify_password("sensitive", hashed) is False


class TestRandomPasswordGeneration:

    def test_default_length_is_12(self, manager):
        assert len(manager.generate_random_password()) == 12

    def test_respects_custom_length(self, manager):
        assert len(manager.generate_random_password(20)) == 20

    def test_two_calls_are_different(self, manager):
        assert manager.generate_random_password() != manager.generate_random_password()

    def test_generated_password_is_itself_verifiable(self, manager):
        """A generated password should work like any other through hash/verify."""
        generated = manager.generate_random_password()
        hashed = manager.hash_password(generated)
        assert manager.verify_password(generated, hashed) is True


class TestGenerateToken:

    def test_default_length_produces_a_nonempty_urlsafe_token(self, manager):
        token = manager.generate_token()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_two_calls_are_different(self, manager):
        assert manager.generate_token() != manager.generate_token()

    def test_respects_custom_length_argument(self, manager):
        """secrets.token_urlsafe(n) derives its string length from the byte length
        n, not a 1:1 char count, so just confirm a larger n yields a longer token."""
        assert len(manager.generate_token(4)) < len(manager.generate_token(64))


class TestModuleLevelConvenienceFunctions:
    """hash_password/verify_password at module level just delegate to PasswordManager."""

    def test_hash_password_delegates_to_password_manager(self):
        hashed = hash_password("a-password")
        assert hashed.startswith("$argon2")

    def test_verify_password_delegates_to_password_manager(self):
        hashed = hash_password("a-password")
        assert verify_password("a-password", hashed) is True
        assert verify_password("wrong-password", hashed) is False
