# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import requests

from .. import cli_param, helper, ub
from ..media import (
    ArtworkStore, ImageDownloadError, ImageTooLargeError, InvalidImageError,
    download_image, read_image_upload,
)

try:
    from .. import cw_advocate
except ImportError:
    cw_advocate = None


def artwork_store():
    return ArtworkStore(ub.app_DB_path, "external_book_covers")


def cover_limit():
    return helper._get_cover_download_limit()[0]


def uploaded_cover(upload, errors, max_bytes):
    try:
        cover = read_image_upload(upload, max_bytes=max_bytes)
    except ImageTooLargeError:
        errors.append("The cover image exceeds the configured size limit.")
        return None
    except InvalidImageError:
        errors.append("Cover images must be JPEG, PNG, or WebP files.")
        return None
    return (cover.data, cover.extension) if cover else None


def remote_cover(url, max_bytes=None):
    if not url:
        return None
    if cli_param.allow_localhost:
        session = requests
    else:
        session = cw_advocate
    if session is None:
        raise ImageDownloadError("Cover downloads require the Advocate network-safety dependency.")
    downloaded = download_image(url, max_bytes=max_bytes or cover_limit(), session=session, timeout=(10, 30))
    return downloaded.data, downloaded.extension
