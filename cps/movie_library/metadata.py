# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""TMDB metadata access. No network request is made without a configured key."""

import os
from datetime import datetime
from urllib.parse import urlparse

import requests

from ..media.images import (
    ImageDownloadError,
    ImageRedirectError,
    ImageTooLargeError,
    InvalidImageError,
    download_image,
    image_type,  # Compatibility export for existing callers/tests.
)

API_ROOT = "https://api.themoviedb.org/3"
POSTER_ROOT = "https://image.tmdb.org/t/p/w500"
MAX_POSTER_BYTES = 8 * 1024 * 1024
PLACEHOLDER_CREDENTIALS = {
    "your_tmdb_read_access_token_here", "your_tmdb_api_key_here",
    "your_token_here", "your_v3_key_here",
}


class MovieMetadataError(Exception):
    """A safe, user-presentable metadata or poster retrieval error."""


def _text(value, default=""):
    return str(value).strip() if value is not None else default


def _poster_url(path):
    path = _text(path)
    if path.startswith("/") and ".." not in path and "\\" not in path:
        return POSTER_ROOT + path
    return ""


def _credential(value):
    value = value.strip()
    return "" if value in PLACEHOLDER_CREDENTIALS else value


class TMDBClient:
    def __init__(self, api_key=None, read_access_token=None, session=None, language=None):
        self.api_key = _credential(api_key if api_key is not None else os.getenv("TMDB_API_KEY", ""))
        self.read_access_token = _credential(
            read_access_token if read_access_token is not None
            else os.getenv("TMDB_READ_ACCESS_TOKEN", "")
        )
        self.language = language or os.getenv("TMDB_LANGUAGE", "en-US")
        self.http = session or requests.Session()
        self.http.headers.update({
            "Accept": "application/json",
            "User-Agent": "HomeLibrary/1.0 (Calibre-Web-Automated)",
        })

    @property
    def configured(self):
        return bool(self.api_key or self.read_access_token)

    def _get(self, path, params=None):
        if not self.configured:
            raise MovieMetadataError(
                "TMDB is not configured. Add TMDB_API_KEY or TMDB_READ_ACCESS_TOKEN to enable online lookup."
            )
        params = dict(params or {})
        headers = {}
        if self.read_access_token:
            headers["Authorization"] = f"Bearer {self.read_access_token}"
        else:
            params["api_key"] = self.api_key
        params.setdefault("language", self.language)
        try:
            response = self.http.get(
                f"{API_ROOT}/{path.lstrip('/')}", params=params, headers=headers, timeout=(5, 15)
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise MovieMetadataError("TMDB could not complete the request. Check the API credentials and network.") from exc
        if not isinstance(payload, dict):
            raise MovieMetadataError("TMDB returned an unexpected response.")
        return payload

    def search(self, query, year=None):
        query = _text(query)
        if not query:
            raise MovieMetadataError("Enter a movie title to search.")
        if len(query) > 200:
            raise MovieMetadataError("The movie title is too long.")
        params = {"query": query, "include_adult": "false", "page": 1}
        if year:
            try:
                year = int(year)
            except (TypeError, ValueError) as exc:
                raise MovieMetadataError("Enter a valid release year.") from exc
            if not 1870 <= year <= datetime.now().year + 5:
                raise MovieMetadataError("Enter a valid release year.")
            params["year"] = year
        payload = self._get("search/movie", params)
        results = payload.get("results", [])
        if not isinstance(results, list):
            return []
        return [self._summary(item) for item in results[:12] if isinstance(item, dict) and item.get("id")]

    @staticmethod
    def _summary(item):
        rating = item.get("vote_average")
        return {
            "tmdb_id": int(item["id"]),
            "title": _text(item.get("title"), "Untitled"),
            "original_title": _text(item.get("original_title")),
            "release_date": _text(item.get("release_date")),
            "year": _text(item.get("release_date"))[:4],
            "overview": _text(item.get("overview")),
            "poster_url": _poster_url(item.get("poster_path")),
            "tmdb_rating": round(float(rating), 1) if isinstance(rating, (int, float)) else None,
        }

    def details(self, tmdb_id):
        try:
            tmdb_id = int(tmdb_id)
        except (TypeError, ValueError) as exc:
            raise MovieMetadataError("Select a valid TMDB result.") from exc
        if tmdb_id <= 0:
            raise MovieMetadataError("Select a valid TMDB result.")
        item = self._get(f"movie/{tmdb_id}", {"append_to_response": "credits,release_dates"})
        summary = self._summary(item)
        credits = item.get("credits") if isinstance(item.get("credits"), dict) else {}
        crew = credits.get("crew", []) if isinstance(credits.get("crew", []), list) else []
        cast = credits.get("cast", []) if isinstance(credits.get("cast", []), list) else []
        genres = item.get("genres", []) if isinstance(item.get("genres", []), list) else []
        runtime = item.get("runtime")
        summary.update({
            "overview": _text(item.get("overview")),
            "director": ", ".join(
                _text(person.get("name")) for person in crew
                if isinstance(person, dict) and person.get("job") == "Director" and person.get("name")
            ),
            "cast_members": ", ".join(
                _text(person.get("name")) for person in cast[:10]
                if isinstance(person, dict) and person.get("name")
            ),
            "genres": ", ".join(
                _text(genre.get("name")) for genre in genres
                if isinstance(genre, dict) and genre.get("name")
            ),
            "runtime": runtime if isinstance(runtime, int) and runtime > 0 else None,
            "imdb_id": _text(item.get("imdb_id")),
            "content_rating": self._content_rating(item.get("release_dates")),
        })
        return summary

    @staticmethod
    def _content_rating(release_dates):
        if not isinstance(release_dates, dict):
            return ""
        countries = release_dates.get("results", [])
        if not isinstance(countries, list):
            return ""
        for country in countries:
            if not isinstance(country, dict) or country.get("iso_3166_1") != "US":
                continue
            releases = country.get("release_dates", [])
            for release in releases if isinstance(releases, list) else []:
                if isinstance(release, dict) and release.get("type") == 3:
                    return _text(release.get("certification"))
        return ""

    def download_poster(self, url):
        """Download a TMDB poster with host, size, and image-format checks."""
        if not self._trusted_poster_url(url):
            raise MovieMetadataError("The poster URL is not a trusted TMDB image URL.")
        if not self.configured:
            raise MovieMetadataError("TMDB is not configured.")
        try:
            downloaded = download_image(
                url, max_bytes=MAX_POSTER_BYTES, session=self.http, timeout=(5, 20),
                url_validator=self._trusted_poster_url,
            )
            return downloaded.data, downloaded.extension
        except ImageRedirectError as exc:
            raise MovieMetadataError("TMDB poster redirects are not followed.") from exc
        except ImageTooLargeError as exc:
            raise MovieMetadataError("The poster exceeds the 8 MB size limit.") from exc
        except InvalidImageError as exc:
            raise MovieMetadataError("TMDB returned an unsupported poster image.") from exc
        except ImageDownloadError as exc:
            raise MovieMetadataError(
                "The movie metadata was saved, but its poster could not be downloaded."
            ) from exc

    @staticmethod
    def _trusted_poster_url(url):
        parsed = urlparse(_text(url))
        return (parsed.scheme == "https" and parsed.hostname == "image.tmdb.org"
                and parsed.path.startswith("/t/p/"))
