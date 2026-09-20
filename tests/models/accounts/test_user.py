"""Tests for models/accounts/user.py computed properties.

is_active and verified are read by require_admin/require_auth and the login flow -
getting the underlying status comparison wrong locks out or lets in the wrong users.
"""

from models.accounts.user import User, AccountStatus, VerificationStatus, Address


def make_user(account_status=AccountStatus.ACTIVE, verification_status=VerificationStatus.UNVERIFIED,
              firstname="Ada", lastname="Lovelace") -> User:
    user = User()
    user.account_status = account_status
    user.verification_status = verification_status
    user.firstname = firstname
    user.lastname = lastname
    user.addresses = []
    return user


class TestFullName:

    def test_combines_first_and_last_name(self):
        assert make_user(firstname="Ada", lastname="Lovelace").full_name == "Ada Lovelace"


class TestIsActive:

    def test_active_status_is_active(self):
        assert make_user(account_status=AccountStatus.ACTIVE).is_active is True

    def test_inactive_status_is_not_active(self):
        assert make_user(account_status=AccountStatus.INACTIVE).is_active is False

    def test_suspended_status_is_not_active(self):
        assert make_user(account_status=AccountStatus.SUSPENDED).is_active is False


class TestVerified:

    def test_verified_status_is_verified(self):
        assert make_user(verification_status=VerificationStatus.VERIFIED).verified is True

    def test_unverified_status_is_not_verified(self):
        assert make_user(verification_status=VerificationStatus.UNVERIFIED).verified is False


class TestDefaultAddress:

    def test_none_when_no_addresses(self):
        assert make_user().default_address is None

    def test_none_when_no_address_is_marked_default(self):
        user = make_user()
        addr = Address()
        addr.is_default = False
        user.addresses = [addr]
        assert user.default_address is None

    def test_returns_the_address_marked_default(self):
        user = make_user()
        not_default = Address()
        not_default.is_default = False
        default = Address()
        default.is_default = True
        user.addresses = [not_default, default]
        assert user.default_address is default
