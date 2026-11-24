# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Optional companion-library links configured through environment variables."""

import os
from urllib.parse import urlparse

_LINKS = (
    ("AUDIOBOOKSHELF_URL", "Audiobookshelf"),
    ("PLEX_URL", "Plex"),
    ("JELLYFIN_URL", "Jellyfin"),
    ("GRIMMORY_URL", "Grimmory"),
)


def library_links():
    links = []
    for variable, label in _LINKS:
        url = os.environ.get(variable, "").strip()
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            continue
        links.append({"label": label, "url": url})
    return links
