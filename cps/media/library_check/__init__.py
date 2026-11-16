# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Ownership checks for metadata search results."""

from .service import annotate_books, annotate_movies, clear_cache

__all__ = ["annotate_books", "annotate_movies", "clear_cache"]
