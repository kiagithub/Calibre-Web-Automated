# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from cps.media.library_check import matcher
from cps.media.library_check.matcher import LibraryEntry, MovieEntry
from cps.media.text_match import author_surname, clean_title_tokens, isbn_variants, significant_tokens


def book_entry(kind="calibre", title="", authors=(), series="", isbns=(), asins=(), external_ids=()):
    title_tokens = clean_title_tokens(title, has_series=bool(series))
    author_tokens = frozenset(
        surname for surname in (author_surname(author) for author in authors) if surname
    )
    series_tokens = frozenset(significant_tokens(series))
    return LibraryEntry(
        kind=kind,
        title_tokens=title_tokens,
        tokens=title_tokens | author_tokens | series_tokens,
        author_tokens=author_tokens,
        series_tokens=series_tokens,
        isbns=frozenset(isbns),
        asins=frozenset(asins),
        external_ids=frozenset(external_ids),
    )


def record(title, authors=(), identifiers=None, source="google", provider_id="1"):
    return {
        "title": title,
        "authors": list(authors),
        "identifiers": identifiers or {},
        "source": {"id": source},
        "id": provider_id,
    }


@pytest.mark.unit
class TestBookMatching:
    def test_external_provider_id_matches(self):
        entries = [book_entry(external_ids={("hardcover", "123")}, title="Something else")]

        assert matcher.match_book(record("Different", source="hardcover", provider_id="123"), entries)

    def test_isbn_10_and_13_match(self):
        entries = [book_entry(isbns=isbn_variants("0-441-17271-7"), title="Dune")]

        assert matcher.match_book(record("Different", identifiers={"isbn": "9780441172719"}), entries)

    def test_exact_title_and_author_match(self):
        entries = [book_entry(title="Dune", authors=["Frank Herbert"])]

        assert matcher.match_book(record("Dune", ["Frank Herbert"]), entries)

    def test_different_author_does_not_match(self):
        entries = [book_entry(title="Dune", authors=["Frank Herbert"])]

        assert matcher.match_book(record("Dune", ["Kevin J. Anderson"]), entries) is None

    def test_sequel_does_not_match(self):
        entries = [book_entry(title="Dune Messiah", authors=["Frank Herbert"])]

        assert matcher.match_book(record("Dune", ["Frank Herbert"]), entries) is None

    def test_printing_edition_words_do_not_block_a_match(self):
        entries = [book_entry(title="Dune: Deluxe Edition", authors=["Frank Herbert"])]

        assert matcher.match_book(record("Dune", ["Frank Herbert"]), entries)

    def test_series_label_is_ignored(self):
        entries = [
            book_entry(
                title="Alex Cross 02: Kiss the Girls",
                authors=["James Patterson"],
                series="Alex Cross",
            )
        ]

        assert matcher.match_book(record("Kiss the Girls", ["James Patterson"]), entries)

    def test_omnibus_is_reported_as_a_collection(self):
        entries = [book_entry(title="Dune: The Complete Collection", authors=["Frank Herbert"])]

        result = matcher.match_book(record("Dune", ["Frank Herbert"]), entries)

        assert result is not None and result.collection is True

    def test_entry_without_author_allows_a_title_match(self):
        entries = [book_entry(title="Dune")]

        assert matcher.match_book(record("Dune", ["Frank Herbert"]), entries)

    def test_annotation_sets_owned_fields(self):
        entries = [book_entry(title="Dune", authors=["Frank Herbert"])]
        results = [record("Dune", ["Frank Herbert"]), record("Hyperion", ["Dan Simmons"])]

        matcher.annotate_books(results, entries)

        assert results[0]["owned"] is True
        assert results[0]["owned_as"] == "Calibre"
        assert results[1]["owned"] is False
        assert results[1]["owned_as"] == ""


@pytest.mark.unit
class TestMovieMatching:
    def entry(self, tmdb_id=1, title="Arrival", year="2016"):
        return MovieEntry(
            tmdb_id=tmdb_id,
            imdb_id="",
            title_tokens=clean_title_tokens(title),
            original_title_tokens=clean_title_tokens(title),
            year=year,
        )

    def test_tmdb_id_matches(self):
        assert matcher.match_movie({"tmdb_id": 1, "title": "Different"}, [self.entry()])

    def test_title_and_year_match(self):
        assert matcher.match_movie({"title": "Arrival", "year": "2016"}, [self.entry()])

    def test_year_mismatch_does_not_match(self):
        assert matcher.match_movie({"title": "Arrival", "year": "2020"}, [self.entry()]) is None

    def test_annotation_sets_owned_fields(self):
        results = [{"title": "Arrival", "year": "2016"}]
        matcher.annotate_movies(results, [self.entry()])
        assert results[0]["owned"] is True
        assert results[0]["owned_as"] == "Movies"
