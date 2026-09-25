"""Tests for services/catalog/review.py - ReviewService.

Covers the ownership checks on update/delete (a review can only be changed
by the user who wrote it), the one-review-per-user-per-product constraint,
and _update_product_rating/recalc_ratings - the aggregation logic that
keeps Product.rating_average/rating_count/review_count in sync.
"""

import pytest
from uuid import uuid4

from core.exceptions import APIException
from services.catalog.review import ReviewService
from services.accounts.auth import AuthService
from schemas.catalog.review import Create as ReviewCreate, Update as ReviewUpdate
from models.catalog.product import Product
from models.accounts.user import User, UserRole


def _async_raiser(exc):
    """Build an async function that always raises `exc` - used to monkeypatch an
    internal collaborator so a specific except-clause body actually runs, matching
    the pattern in tests/services/commerce/test_payments.py."""
    async def _raise(*args, **kwargs):
        raise exc
    return _raise


async def make_product(db_session, **overrides) -> Product:
    fields = {
        "id": uuid4(),
        "name": "Test Product",
        "slug": f"test-product-{uuid4().hex[:8]}",
    }
    fields.update(overrides)
    product = Product(**fields)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


async def make_user(db_session, **overrides) -> User:
    auth = AuthService(db_session)
    fields = {
        "id": uuid4(),
        "email": f"review_test_{uuid4().hex[:8]}@example.com",
        "firstname": "Test",
        "lastname": "Reviewer",
        "hashed_password": auth.get_password_hash("Password123!"),
        "role": UserRole.CUSTOMER,
        "account_status": "active",
        "verification_status": "verified",
    }
    fields.update(overrides)
    user = User(**fields)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


class TestCreate:

    async def test_creates_a_review(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        result = await service.create(ReviewCreate(product_id=product.id, rating=5, comment="Great!"), user.id)
        assert result["rating"] == 5
        assert result["comment"] == "Great!"

    async def test_updates_product_rating_average_and_count(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        await service.create(ReviewCreate(product_id=product.id, rating=4), user.id)

        await db_session.refresh(product)
        assert float(product.rating_average) == pytest.approx(4.0)
        assert product.rating_count == 1
        assert product.review_count == 1

    async def test_unknown_product_is_rejected(self, db_session):
        user = await make_user(db_session)
        service = ReviewService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.create(ReviewCreate(product_id=uuid4(), rating=3), user.id)
        assert exc_info.value.status_code == 404

    async def test_duplicate_review_by_same_user_is_rejected(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        await service.create(ReviewCreate(product_id=product.id, rating=5), user.id)
        with pytest.raises(APIException) as exc_info:
            await service.create(ReviewCreate(product_id=product.id, rating=1), user.id)
        assert exc_info.value.status_code == 400

    async def test_create_succeeds_even_if_rating_aggregation_fails(self, db_session, monkeypatch):
        """create() deliberately doesn't fail the request if the post-write rating
        recompute blows up - the review itself is already committed and more
        important than the aggregate staying perfectly in sync."""
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        monkeypatch.setattr(service, "_update_product_rating", _async_raiser(RuntimeError("boom")))

        result = await service.create(ReviewCreate(product_id=product.id, rating=5, comment="Still works"), user.id)
        assert result["rating"] == 5

        # The review itself was really persisted despite the rating update failing.
        found = await service.get(result["id"])
        assert found is not None


class TestGet:

    async def test_gets_by_id(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        created = await service.create(ReviewCreate(product_id=product.id, rating=3), user.id)
        found = await service.get(created["id"])
        assert str(found.id) == created["id"]

    async def test_unknown_id_returns_none(self, db_session):
        service = ReviewService(db_session)
        assert await service.get(uuid4()) is None


class TestList:

    async def test_lists_with_pagination_envelope(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        await service.create(ReviewCreate(product_id=product.id, rating=4), user.id)

        result = await service.list(product_id=product.id)
        assert result["total"] == 1
        assert result["page"] == 1
        assert len(result["data"]) == 1

    async def test_filters_by_rating_range(self, db_session):
        product = await make_product(db_session)
        service = ReviewService(db_session)
        for rating in (1, 3, 5):
            user = await make_user(db_session)
            await service.create(ReviewCreate(product_id=product.id, rating=rating), user.id)

        result = await service.list(product_id=product.id, min_rating=3, max_rating=5)
        assert result["total"] == 2

    async def test_sort_by_invalid_field_falls_back_to_default(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        await service.create(ReviewCreate(product_id=product.id, rating=4), user.id)

        result = await service.list(product_id=product.id, sort_by="not_a_real_field_desc")
        assert result["total"] == 1

    async def test_sort_by_invalid_order_falls_back_to_default(self, db_session):
        """sort_field is valid ('rating') but the trailing direction isn't asc/desc."""
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        await service.create(ReviewCreate(product_id=product.id, rating=4), user.id)

        result = await service.list(product_id=product.id, sort_by="rating_sideways")
        assert result["total"] == 1

    async def test_sort_by_rating_ascending(self, db_session):
        product = await make_product(db_session)
        service = ReviewService(db_session)
        for rating in (5, 1, 3):
            user = await make_user(db_session)
            await service.create(ReviewCreate(product_id=product.id, rating=rating), user.id)

        result = await service.list(product_id=product.id, sort_by="rating_asc")
        assert [r.rating for r in result["data"]] == [1, 3, 5]


class TestUpdate:

    async def test_owner_can_update(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        created = await service.create(ReviewCreate(product_id=product.id, rating=2), user.id)

        updated = await service.update(created["id"], ReviewUpdate(rating=5, comment="Actually great"), user.id)
        assert updated.rating == 5
        assert updated.comment == "Actually great"

    async def test_update_refreshes_product_rating(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        created = await service.create(ReviewCreate(product_id=product.id, rating=1), user.id)
        await service.update(created["id"], ReviewUpdate(rating=5), user.id)

        await db_session.refresh(product)
        assert float(product.rating_average) == pytest.approx(5.0)

    async def test_unknown_id_raises_404(self, db_session):
        user = await make_user(db_session)
        service = ReviewService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.update(uuid4(), ReviewUpdate(rating=3), user.id)
        assert exc_info.value.status_code == 404

    async def test_non_owner_cannot_update(self, db_session):
        product = await make_product(db_session)
        owner = await make_user(db_session)
        other = await make_user(db_session)
        service = ReviewService(db_session)
        created = await service.create(ReviewCreate(product_id=product.id, rating=4), owner.id)

        with pytest.raises(APIException) as exc_info:
            await service.update(created["id"], ReviewUpdate(rating=1), other.id)
        assert exc_info.value.status_code == 403


class TestDelete:

    async def test_owner_can_delete(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        created = await service.create(ReviewCreate(product_id=product.id, rating=3), user.id)

        await service.delete(created["id"], user.id)
        assert await service.get(created["id"]) is None

    async def test_other_customer_cannot_delete(self, db_session):
        product = await make_product(db_session)
        author, other = await make_user(db_session), await make_user(db_session)
        service = ReviewService(db_session)
        created = await service.create(ReviewCreate(product_id=product.id, rating=3), author.id)
        with pytest.raises(APIException) as exc_info:
            await service.delete(created["id"], other.id)
        assert exc_info.value.status_code == 403

    async def test_staff_can_delete_any_review(self, db_session):
        product = await make_product(db_session)
        author, staff = await make_user(db_session), await make_user(db_session)
        service = ReviewService(db_session)
        created = await service.create(ReviewCreate(product_id=product.id, rating=3), author.id)
        await service.delete(created["id"], staff.id, is_admin=True)
        assert await service.get(created["id"]) is None

    async def test_delete_updates_product_rating_count(self, db_session):
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        created = await service.create(ReviewCreate(product_id=product.id, rating=3), user.id)

        await service.delete(created["id"], user.id)
        await db_session.refresh(product)
        assert product.review_count == 0

    async def test_unknown_id_raises_404(self, db_session):
        user = await make_user(db_session)
        service = ReviewService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.delete(uuid4(), user.id)
        assert exc_info.value.status_code == 404

    async def test_non_owner_cannot_delete(self, db_session):
        product = await make_product(db_session)
        owner = await make_user(db_session)
        other = await make_user(db_session)
        service = ReviewService(db_session)
        created = await service.create(ReviewCreate(product_id=product.id, rating=4), owner.id)

        with pytest.raises(APIException) as exc_info:
            await service.delete(created["id"], other.id)
        assert exc_info.value.status_code == 403


class TestUpdateProductRatingInternal:

    async def test_reraises_after_logging_on_failure(self, db_session, monkeypatch):
        """_update_product_rating logs and re-raises rather than swallowing - it's
        create() (the only caller that tolerates a failed aggregate) that decides
        to swallow it; update()/delete() let it propagate."""
        product = await make_product(db_session)
        user = await make_user(db_session)
        service = ReviewService(db_session)
        await service.create(ReviewCreate(product_id=product.id, rating=4), user.id)

        monkeypatch.setattr(db_session, "commit", _async_raiser(RuntimeError("boom")))
        with pytest.raises(RuntimeError):
            await service._update_product_rating(product.id)


