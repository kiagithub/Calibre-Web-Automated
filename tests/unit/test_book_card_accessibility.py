# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

import pytest
from jinja2 import Environment

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_book_cards_use_shared_markup_without_repeated_loop_ids():
    index = (REPO / "cps/templates/index.html").read_text()
    author = (REPO / "cps/templates/author.html").read_text()
    assert 'id="books"' not in index
    assert 'id="books_rand"' not in index
    assert 'id="books"' not in author
    assert index.count("book_cards.calibre_book_card(") == 2
    assert author.count("book_cards.calibre_book_card(") == 1
    assert "entry.Books" not in index
    assert "entry.Books" not in author
    for template in ("index.html", "author.html", "components/calibre_book_card.html"):
        Environment().parse((REPO / "cps/templates" / template).read_text())


@pytest.mark.unit
def test_book_quick_actions_are_native_and_not_pointer_coordinate_based():
    script = (REPO / "cps/static/js/caliBlur.js").read_text()
    assert 'type="button" class="book-quick-action"' in script
    assert "$cover.append(actionButton(" in script
    assert "mousemove.directReading" not in script
    assert "click.directReading" not in script
    assert "Math.sqrt" not in script
    assert "aria-pressed" in script
    assert "aria-busy" in script


@pytest.mark.unit
def test_focus_and_collapsed_navigation_have_semantic_contracts():
    layout = (REPO / "cps/templates/layout.html").read_text()
    cali_blur = (REPO / "cps/static/css/caliBlur.css").read_text()
    assert 'id="nav_home"' in layout
    assert "nav_{{ primary_books['id'] }}" in layout
    assert 'id="nav_movies"' in layout
    assert "<details" in layout and "<summary" in layout
    assert '<ul class="pagination" aria-label=' in layout
    assert "a:focus {\n    outline: 0" not in cali_blur
    assert ".cover:focus-within .book-quick-action" in cali_blur
    Environment().parse(layout)
