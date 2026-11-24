# -*- coding: utf-8 -*-
# Calibre-Web Automated – fork of Calibre-Web
# Copyright (C) 2024-2025 Calibre-Web Automated contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# See CONTRIBUTORS for full list of authors.

import pytest
import sys
import os
from urllib.parse import parse_qs, urlparse

from flask import Flask

# Add the parent directory to the path so we can import cps modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from cps.jinjia import formatfloat, url_for_other_page


class TestFormatFloatFilter:
    """Tests for the formatfloat Jinja2 filter"""

    def test_formatfloat_with_float(self):
        """Test formatfloat with float input"""
        assert formatfloat(1.5, 2) == '1.5'
        assert formatfloat(1.0, 2) == '1'
        assert formatfloat(1.234, 2) == '1.23'
        assert formatfloat(10.999, 2) == '11'

    def test_formatfloat_with_string(self):
        """Test formatfloat with string input (as stored in DB)"""
        assert formatfloat('1.5', 2) == '1.5'
        assert formatfloat('1.0', 2) == '1'
        assert formatfloat('1.234', 2) == '1.23'
        assert formatfloat('10.999', 2) == '11'

    def test_formatfloat_with_zero(self):
        """Test formatfloat with zero values"""
        assert formatfloat(0, 2) == '0'
        assert formatfloat(0.0, 2) == '0'
        assert formatfloat('0', 2) == '0'
        assert formatfloat('0.0', 2) == '0'
        assert formatfloat('0.00', 2) == '0'

    def test_formatfloat_with_none(self):
        """Test formatfloat with None"""
        assert formatfloat(None, 2) == ''

    def test_formatfloat_with_empty_string(self):
        """Test formatfloat with empty string"""
        assert formatfloat('', 2) == ''
        assert formatfloat('  ', 2) == ''

    def test_formatfloat_with_invalid_string(self):
        """Test formatfloat with non-numeric string - should return empty string"""
        assert formatfloat('invalid', 2) == ''
        assert formatfloat('abc', 2) == ''
        assert formatfloat('1.2.3', 2) == ''

    def test_formatfloat_with_different_decimals(self):
        """Test formatfloat with different decimal precision"""
        assert formatfloat(1.5, 1) == '1.5'
        assert formatfloat(1.5, 3) == '1.5'
        assert formatfloat(1.12345, 4) == '1.1235'  # rounds up
        assert formatfloat('3.14159', 2) == '3.14'

    def test_formatfloat_removes_trailing_zeros(self):
        """Test that formatfloat removes trailing zeros"""
        assert formatfloat(1.00, 2) == '1'
        assert formatfloat(1.10, 2) == '1.1'
        assert formatfloat(1.20, 2) == '1.2'
        assert formatfloat('2.00', 2) == '2'

    def test_formatfloat_integer_input(self):
        """Test formatfloat with integer input"""
        assert formatfloat(1, 2) == '1'
        assert formatfloat(10, 2) == '10'
        assert formatfloat(100, 2) == '100'

    def test_formatfloat_negative_numbers(self):
        """Test formatfloat with negative numbers"""
        assert formatfloat(-1.5, 2) == '-1.5'
        assert formatfloat('-1.5', 2) == '-1.5'
        assert formatfloat(-1.0, 2) == '-1'


class TestPaginationUrlFilter:
    def test_query_page_is_replaced_and_filters_are_preserved(self):
        app = Flask(__name__)
        app.add_url_rule("/books/", endpoint="catalog.index", view_func=lambda: url_for_other_page(3))
        result = app.test_client().get("/books/?page=1&q=Arrival&media_type=kindle&tag=Owned").get_data(as_text=True)
        assert parse_qs(urlparse(result).query) == {
            "q": ["Arrival"], "media_type": ["kindle"], "tag": ["Owned"], "page": ["3"]
        }

    def test_route_arguments_are_preserved(self):
        app = Flask(__name__)
        app.add_url_rule(
            "/newest/<sort_param>/<book_id>/<int:page>", endpoint="web.books_list",
            view_func=lambda **_kwargs: url_for_other_page(4),
        )
        result = app.test_client().get("/newest/stored/1/2?query=Arrival").get_data(as_text=True)
        assert result == "/newest/stored/1/4?query=Arrival"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
