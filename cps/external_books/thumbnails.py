# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Small, cached cover thumbnails for metadata search results."""

import re
import threading
import time
from collections import OrderedDict
from urllib.parse import urlparse

from .. import logger
from ..media import ImageDownloadError
from .covers import cover_limit, remote_cover

try:
    from wand.color import Color as WandColor
    from wand.image import Image as WandImage
except (ImportError, RuntimeError):
    WandColor = None
    WandImage = None

THUMBNAIL_WIDTH = 160
THUMBNAIL_HEIGHT = 240
THUMBNAIL_QUALITY = 82
THUMBNAIL_DOWNLOAD_LIMIT = 6 * 1024 * 1024
THUMBNAIL_CACHE_TTL = 3600
THUMBNAIL_CACHE_SIZE = 256
THUMBNAIL_MAX_CACHE_BYTES = 256 * 1024

_CONTENT_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
_GOOGLE_FIFE = re.compile(r"([?&])fife=w\d+-h\d+")

_thumbnail_cache = OrderedDict()
_cache_lock = threading.Lock()
log = logger.create()


def valid_cover_url(url):
    """Return whether a URL is safe to hand to the bounded image downloader."""
    url = str(url or "").strip()
    if not url or len(url) > 2000:
        return False
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in ("http", "https")
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
        and port in (None, 80, 443)
    )


def _thumbnail_source(url):
    """Prefer a provider's preview-sized image so less data is downloaded."""
    if "books.google" in url:
        return _GOOGLE_FIFE.sub(r"\1fife=w200-h300", url)
    return url


def download_cover(url):
    """Download a cover using the same safe network policy as saved covers."""
    limit = min(cover_limit(), THUMBNAIL_DOWNLOAD_LIMIT)
    return remote_cover(_thumbnail_source(url), max_bytes=limit)


def _resize(data, extension):
    """Shrink an image to thumbnail size, falling back to the original bytes."""
    fallback_type = _CONTENT_TYPES.get(extension, "application/octet-stream")
    if WandImage is None:
        return data, fallback_type
    try:
        with WandImage(blob=data) as image:
            if image.alpha_channel:
                image.alpha_channel = "remove"
                image.background_color = WandColor("white")
            image.thumbnail(width=THUMBNAIL_WIDTH, height=THUMBNAIL_HEIGHT)
            image.format = "jpeg"
            image.quality = THUMBNAIL_QUALITY
            return image.make_blob(), "image/jpeg"
    except Exception:
        return data, fallback_type


def metadata_thumbnail(url, now=None):
    """Return ``(image_bytes, content_type)`` for a result cover, or ``None``.

    Thumbnails are cached in memory so the browser can request the same cover
    repeatedly without triggering another provider download.
    """
    url = str(url or "").strip()
    if not valid_cover_url(url):
        return None
    now = time.monotonic() if now is None else now
    with _cache_lock:
        entry = _thumbnail_cache.get(url)
        if entry is not None:
            expires, data, content_type = entry
            if expires > now:
                _thumbnail_cache.move_to_end(url)
                return data, content_type
            _thumbnail_cache.pop(url, None)
    try:
        downloaded = download_cover(url)
    except ImageDownloadError:
        return None
    except Exception as exc:
        log.warning("Could not build metadata thumbnail for %s: %s", url, exc)
        return None
    if not downloaded:
        return None
    data, content_type = _resize(*downloaded)
    if len(data) <= THUMBNAIL_MAX_CACHE_BYTES:
        with _cache_lock:
            _thumbnail_cache[url] = (now + THUMBNAIL_CACHE_TTL, data, content_type)
            _thumbnail_cache.move_to_end(url)
            while len(_thumbnail_cache) > THUMBNAIL_CACHE_SIZE:
                _thumbnail_cache.popitem(last=False)
    return data, content_type


def clear_thumbnail_cache():
    """Test helper: forget every cached thumbnail."""
    with _cache_lock:
        _thumbnail_cache.clear()
