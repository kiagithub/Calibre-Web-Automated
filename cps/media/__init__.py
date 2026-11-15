# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared infrastructure for physical and external media catalogs."""

from .artwork import ArtworkStore, serve_artwork
from .images import (
    DownloadedImage,
    ImageDownloadError,
    ImageRedirectError,
    ImageTooLargeError,
    InvalidImageError,
    LocalAddressError,
    download_image,
    image_type,
    read_image_upload,
)
from .permissions import media_delete_required, media_edit_required, media_permissions

__all__ = [
    "ArtworkStore", "serve_artwork", "DownloadedImage", "ImageDownloadError", "ImageRedirectError",
    "ImageTooLargeError", "InvalidImageError", "LocalAddressError", "download_image",
    "image_type", "read_image_upload", "media_delete_required", "media_edit_required", "media_permissions",
]
