"""Tests for core/utils/uuid_utils.py - UUIDv7 generation and helpers."""

import time
import uuid

from core.utils.uuid_utils import (
    uuid7,
    uuid7_str,
    is_uuid7,
    extract_timestamp_from_uuid7,
    uuid7_from_timestamp,
)


class TestUUID7Generation:

    def test_returns_uuid_instance(self):
        assert isinstance(uuid7(), uuid.UUID)

    def test_version_is_7(self):
        assert uuid7().version == 7

    def test_variant_bits_are_rfc4122(self):
        # RFC 4122 variant: the two most significant bits of byte 8 are "10"
        value = uuid7()
        assert (value.bytes[8] & 0xC0) == 0x80

    def test_two_calls_are_unique(self):
        assert uuid7() != uuid7()

    def test_str_helper_matches_uuid_str(self):
        s = uuid7_str()
        assert isinstance(s, str)
        assert uuid.UUID(s).version == 7

    def test_sortable_by_creation_time(self):
        """The entire point of UUIDv7 over UUIDv4: lexicographic order tracks creation order."""
        first = uuid7()
        time.sleep(0.005)
        second = uuid7()
        assert str(first) < str(second)


class TestIsUUID7:

    def test_true_for_a_real_uuid7(self):
        assert is_uuid7(uuid7()) is True

    def test_true_for_a_uuid7_string(self):
        assert is_uuid7(uuid7_str()) is True

    def test_false_for_uuid4(self):
        assert is_uuid7(uuid.uuid4()) is False

    def test_false_for_garbage_string(self):
        assert is_uuid7("not-a-uuid") is False


class TestTimestampRoundTrip:

    def test_extracted_timestamp_matches_generation_time(self):
        before = int(time.time() * 1000)
        value = uuid7()
        after = int(time.time() * 1000)

        extracted = extract_timestamp_from_uuid7(value)
        assert before <= extracted <= after

    def test_accepts_string_input(self):
        value = uuid7()
        assert extract_timestamp_from_uuid7(str(value)) == extract_timestamp_from_uuid7(value)

    def test_zero_for_non_uuid7(self):
        assert extract_timestamp_from_uuid7(uuid.uuid4()) == 0

    def test_zero_for_invalid_string(self):
        assert extract_timestamp_from_uuid7("nonsense") == 0

    def test_uuid7_from_timestamp_round_trips(self):
        ts = 1_700_000_000_000  # arbitrary fixed millisecond timestamp
        generated = uuid7_from_timestamp(ts)
        assert is_uuid7(generated)
        assert extract_timestamp_from_uuid7(generated) == ts

    def test_uuid7_from_timestamp_is_random_past_the_timestamp(self):
        ts = 1_700_000_000_000
        a = uuid7_from_timestamp(ts)
        b = uuid7_from_timestamp(ts)
        assert a != b  # same timestamp, different random tail
