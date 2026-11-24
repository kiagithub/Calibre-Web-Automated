# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import datetime, timezone
from pathlib import Path

import pytest

from cps.catalog.service import decode_cursor, encode_cursor
from cps.pagination import KeysetPagination

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_cursor_round_trips_and_rejects_malformed_values():
    timestamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    cursor = encode_cursor(timestamp, "external", 42)

    assert decode_cursor(cursor) == (timestamp, "external", 42)
    assert decode_cursor("not-a-cursor") is None
    assert decode_cursor("") is None
    assert decode_cursor("x" * 501) is None


@pytest.mark.unit
def test_keyset_pagination_exposes_previous_and_next_links():
    pagination = KeysetPagination(prev_url="/books/?cursor=a&dir=prev", next_url="/books/?cursor=b&dir=next")

    assert pagination.keyset is True
    assert pagination.has_prev is True
    assert pagination.has_next is True

    empty = KeysetPagination()
    assert empty.has_prev is False
    assert empty.has_next is False


@pytest.mark.unit
def test_layout_uses_keyset_controls_before_numbered_pagination():
    layout = (REPO_ROOT / "cps" / "templates" / "layout.html").read_text(encoding="utf-8")

    assert "pagination.keyset" in layout
    assert layout.index("pagination.keyset") < layout.index("pagination.iter_pages()")
    assert "pagination.prev_url" in layout
    assert "pagination.next_url" in layout
