# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Open Library metadata provider (public, no API key required)."""

from typing import List, Optional

import requests

from cps import logger
from cps.isoLanguages import get_lang3, get_language_name
from cps.services.Metadata import MetaRecord, MetaSourceInfo, Metadata

log = logger.create()


class OpenLibrary(Metadata):
    __name__ = "Open Library"
    __id__ = "openlibrary"
    DESCRIPTION = "Open Library"
    META_URL = "https://openlibrary.org/"
    SEARCH_URL = "https://openlibrary.org/search.json"
    FIELDS = (
        "key,title,author_name,first_publish_year,publish_year,isbn,cover_i,"
        "language,publisher,subject,series,ratings_average,ratings_count"
    )

    def search(
        self, query: str, generic_cover: str = "", locale: str = "en"
    ) -> Optional[List[MetaRecord]]:
        if not self.active or not query:
            return []
        try:
            response = requests.get(
                self.SEARCH_URL,
                params={"q": query, "limit": 12, "fields": self.FIELDS},
                headers={"User-Agent": "Calibre-Web-Automated"},
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            log.warning("Open Library search failed: %s", exc)
            return []
        docs = payload.get("docs") if isinstance(payload, dict) else []
        if not isinstance(docs, list):
            docs = []
        records = []
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            record = self._parse_record(doc, generic_cover, locale)
            if record:
                records.append(record)
        return records

    def _parse_record(self, doc, generic_cover, locale):
        title = str(doc.get("title") or "").strip()
        key = str(doc.get("key") or "").strip()
        if not title or not key:
            return None
        work_id = key.rstrip("/").rsplit("/", 1)[-1]
        authors = doc.get("author_name") or []
        if isinstance(authors, str):
            authors = [authors]
        cover_id = doc.get("cover_i")
        cover = (
            f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
            if cover_id
            else generic_cover
        )
        publisher = doc.get("publisher") or []
        if isinstance(publisher, str):
            publisher = [publisher]
        first_year = doc.get("first_publish_year")
        if not first_year:
            years = doc.get("publish_year") or []
            first_year = years[0] if years else ""
        series = doc.get("series") or []
        if isinstance(series, str):
            series = [series]
        subjects = doc.get("subject") or []
        if isinstance(subjects, str):
            subjects = [subjects]
        record = MetaRecord(
            id=work_id,
            title=title,
            authors=[str(author) for author in authors if author],
            url=f"https://openlibrary.org{key}",
            source=MetaSourceInfo(
                id=self.__id__, description=self.DESCRIPTION, link=self.META_URL
            ),
            cover=cover,
            description="",
            publisher=str(publisher[0]) if publisher else "",
            publishedDate=str(first_year) if first_year else "",
            series=str(series[0]) if series else "",
            series_index=1,
            languages=self._languages(doc.get("language"), locale),
            tags=[str(subject) for subject in subjects[:10]],
            rating=doc.get("ratings_average") or 0,
        )
        record.identifiers = {"openlibrary": work_id}
        isbns = doc.get("isbn") or []
        for isbn in isbns:
            value = str(isbn).strip()
            if len(value) == 13:
                record.identifiers.setdefault("isbn", value)
                record.identifiers.setdefault("isbn_13", value)
            elif len(value) == 10:
                record.identifiers.setdefault("isbn_10", value)
        return record

    @staticmethod
    def _languages(values, locale):
        if isinstance(values, str):
            values = [values]
        languages = []
        for value in values or []:
            code = str(value).strip().lower().rsplit("/", 1)[-1]
            if not code:
                continue
            code = get_lang3(code) if len(code) == 2 else code
            name = get_language_name(locale, code)
            if name and name != "Unknown" and name not in languages:
                languages.append(name)
        return languages
