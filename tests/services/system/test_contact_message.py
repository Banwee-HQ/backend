"""Tests for services/system/contact_message.py - ContactMessageService.

All methods are staticmethods taking db as the first argument. Covers CRUD,
list() pagination/filtering (status, priority, search across name/email/
subject/message), and update()'s resolved_at side effect.
"""

import pytest
from uuid import uuid4

from services.system.contact_message import ContactMessageService
from schemas.system.contact_message import Create as ContactMessageCreate, Update as ContactMessageUpdate


def make_create(**overrides) -> ContactMessageCreate:
    fields = {
        "name": "Jane Doe",
        "email": f"contact_{uuid4().hex[:8]}@example.com",
        "subject": "A question",
        "message": "This is a long enough message body for validation.",
    }
    fields.update(overrides)
    return ContactMessageCreate(**fields)


class TestCreate:

    async def test_creates_with_default_status_and_priority(self, db_session):
        message = await ContactMessageService.create(db_session, make_create())
        assert message.status == "new"
        assert message.priority == "medium"
        assert message.id is not None


class TestGet:

    async def test_gets_by_id(self, db_session):
        created = await ContactMessageService.create(db_session, make_create())
        found = await ContactMessageService.get(db_session, created.id)
        assert found.id == created.id

    async def test_unknown_id_returns_none(self, db_session):
        assert await ContactMessageService.get(db_session, uuid4()) is None


class TestList:

    async def test_lists_with_total_count(self, db_session):
        marker = uuid4().hex[:8]
        await ContactMessageService.create(db_session, make_create(subject=f"ListMe{marker}"))
        messages, total = await ContactMessageService.list(db_session, search=f"ListMe{marker}")
        assert total == 1
        assert messages[0].subject == f"ListMe{marker}"

    async def test_filters_by_status_string(self, db_session):
        marker = uuid4().hex[:8]
        created = await ContactMessageService.create(db_session, make_create(subject=f"StatusFilter{marker}"))
        await ContactMessageService.update(db_session, created.id, ContactMessageUpdate(status="resolved"))

        messages, total = await ContactMessageService.list(db_session, status="resolved", search=f"StatusFilter{marker}")
        assert total == 1

        messages, total = await ContactMessageService.list(db_session, status="new", search=f"StatusFilter{marker}")
        assert total == 0

    async def test_filters_by_priority(self, db_session):
        marker = uuid4().hex[:8]
        created = await ContactMessageService.create(db_session, make_create(subject=f"PriorityFilter{marker}"))
        await ContactMessageService.update(db_session, created.id, ContactMessageUpdate(priority="urgent"))

        messages, total = await ContactMessageService.list(db_session, priority="urgent", search=f"PriorityFilter{marker}")
        assert total == 1

    async def test_search_matches_email(self, db_session):
        created = await ContactMessageService.create(db_session, make_create())
        messages, total = await ContactMessageService.list(db_session, search=created.email)
        assert total == 1

    async def test_search_matches_message_body(self, db_session):
        marker = uuid4().hex[:8]
        await ContactMessageService.create(db_session, make_create(message=f"Unique body content {marker} for search"))
        messages, total = await ContactMessageService.list(db_session, search=marker)
        assert total == 1

    async def test_pagination_limits_page_size(self, db_session):
        marker = uuid4().hex[:8]
        for i in range(3):
            await ContactMessageService.create(db_session, make_create(subject=f"Page{marker}-{i}"))

        page1, total = await ContactMessageService.list(db_session, page=1, page_size=2, search=f"Page{marker}")
        assert total == 3
        assert len(page1) == 2

        page2, total = await ContactMessageService.list(db_session, page=2, page_size=2, search=f"Page{marker}")
        assert len(page2) == 1


class TestUpdate:

    async def test_updates_admin_notes_and_assigned_to(self, db_session):
        created = await ContactMessageService.create(db_session, make_create())
        assignee = uuid4()
        updated = await ContactMessageService.update(
            db_session, created.id, ContactMessageUpdate(admin_notes="Looking into it", assigned_to=assignee)
        )
        assert updated.admin_notes == "Looking into it"
        assert updated.assigned_to == assignee

    async def test_setting_status_resolved_sets_resolved_at(self, db_session):
        created = await ContactMessageService.create(db_session, make_create())
        assert created.resolved_at is None

        updated = await ContactMessageService.update(db_session, created.id, ContactMessageUpdate(status="resolved"))
        assert updated.status == "resolved"
        assert updated.resolved_at is not None

    async def test_non_resolved_status_does_not_set_resolved_at(self, db_session):
        created = await ContactMessageService.create(db_session, make_create())
        updated = await ContactMessageService.update(db_session, created.id, ContactMessageUpdate(status="in_progress"))
        assert updated.resolved_at is None

    async def test_unknown_id_returns_none(self, db_session):
        result = await ContactMessageService.update(db_session, uuid4(), ContactMessageUpdate(status="closed"))
        assert result is None


class TestDelete:

    async def test_deletes_a_message(self, db_session):
        created = await ContactMessageService.create(db_session, make_create())
        assert await ContactMessageService.delete(db_session, created.id) is True
        assert await ContactMessageService.get(db_session, created.id) is None

    async def test_unknown_id_returns_false(self, db_session):
        assert await ContactMessageService.delete(db_session, uuid4()) is False


class TestCreateDbError:

    async def test_null_constraint_violation_rolls_back_and_reraises(self, db_session, mocker):
        """Bypass pydantic validation (model_construct) to smuggle a None past the
        service's own checks, so the real NOT NULL column constraint on `name`
        fires at commit time - a genuine DB error, not a mock. Only the session's
        own rollback() is spied on to confirm the except branch actually ran;
        re-querying the same session afterward is deliberately avoided since a
        raw asyncpg-level error inside this fixture's SAVEPOINT-joined session
        leaves the low-level connection in a state where a *new* query needs a
        fresh session, not a spurious extra thing to assert here."""
        rollback_spy = mocker.spy(db_session, "rollback")
        bad_data = ContactMessageCreate.model_construct(
            name=None, email=f"bad_{uuid4().hex[:8]}@example.com", subject="Subject", message="A long enough message."
        )
        with pytest.raises(Exception):
            await ContactMessageService.create(db_session, bad_data)

        rollback_spy.assert_called_once()


class TestUpdateDbError:

    async def test_invalid_enum_value_rolls_back_and_reraises(self, db_session, mocker):
        """Bypass pydantic's MessageStatus enum validation to write a status value
        the DB's `messagestatus` enum type doesn't accept - a genuine DB-level error."""
        created = await ContactMessageService.create(db_session, make_create())
        rollback_spy = mocker.spy(db_session, "rollback")
        bad_update = ContactMessageUpdate.model_construct(
            status="not_a_real_status", priority=None, admin_notes=None, assigned_to=None
        )
        with pytest.raises(Exception):
            await ContactMessageService.update(db_session, created.id, bad_update)

        rollback_spy.assert_called_once()


class TestDeleteDbError:

    async def test_commit_failure_rolls_back_and_reraises(self, db_session, mocker):
        """No FK references contact_messages, so there's no naturally-occurring DB
        error on delete; simulate a commit-time failure (e.g. connection drop) to
        cover the rollback/reraise branch."""
        created = await ContactMessageService.create(db_session, make_create())
        mocker.patch.object(db_session, "commit", side_effect=RuntimeError("connection lost"))

        with pytest.raises(RuntimeError):
            await ContactMessageService.delete(db_session, created.id)
