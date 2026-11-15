# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validated, bounded image downloads shared by media providers."""

import socket
from dataclasses import dataclass
from typing import Callable, Optional

import requests

from ..cw_advocate.exceptions import UnacceptableAddressException


class ImageDownloadError(Exception):
    """A safe, user-presentable image download error."""

    code = "download"

    def __init__(self, message="The image could not be downloaded."):
        super().__init__(message)


class ImageRedirectError(ImageDownloadError):
    code = "redirect"

    def __init__(self, message="Image redirects are not followed."):
        super().__init__(message)


class ImageTooLargeError(ImageDownloadError):
    code = "size"

    def __init__(self, message="The image exceeds the configured size limit."):
        super().__init__(message)


class InvalidImageError(ImageDownloadError):
    code = "image"

    def __init__(self, message="The response is not a supported JPEG, PNG, or WebP image."):
        super().__init__(message)


class LocalAddressError(ImageDownloadError):
    code = "local_address"

    def __init__(self, message="Localhost and local network image downloads are not allowed."):
        super().__init__(message)


@dataclass(frozen=True)
class DownloadedImage:
    data: bytes
    extension: Optional[str]
    content_type: str = ""

    def __iter__(self):
        """Allow the convenient ``data, extension = download_image(...)`` form."""
        yield self.data
        yield self.extension


def image_type(data):
    """Return a safe extension for supported image bytes, or None."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def read_image_upload(upload, *, max_bytes):
    """Read and validate an uploaded image with the same policy as downloads."""
    if not upload or not upload.filename:
        return None
    data = upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ImageTooLargeError("The uploaded image exceeds the configured size limit.")
    extension = image_type(data)
    if not extension:
        raise InvalidImageError()
    return DownloadedImage(data, extension, getattr(upload, "mimetype", "") or "")


def download_image(url, *, max_bytes, session=None, timeout=(10, 30),
                   url_validator: Optional[Callable[[str], bool]] = None,
                   validate_image=True):
    """Download an image without redirects, enforcing declared and actual size.

    The caller controls network policy by injecting a session. Generic remote
    covers should use an Advocate-backed session unless local addresses were
    explicitly enabled. The response is always closed.
    """
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    url = str(url).strip() if url is not None else ""
    if url_validator is not None and not url_validator(url):
        raise ImageDownloadError("The image URL is not allowed.")
    http = session or requests
    response = None
    try:
        response = http.get(url, stream=True, timeout=timeout, allow_redirects=False)
        if 300 <= response.status_code < 400:
            raise ImageRedirectError()
        response.raise_for_status()
        headers = getattr(response, "headers", {}) or {}
        content_length = headers.get("content-length")
        if content_length and str(content_length).isdigit() and int(content_length) > max_bytes:
            raise ImageTooLargeError()
        chunks = []
        size = 0
        for chunk in response.iter_content(64 * 1024):
            if not chunk:
                continue
            size += len(chunk)
            if size > max_bytes:
                raise ImageTooLargeError()
            chunks.append(chunk)
        data = b"".join(chunks)
        extension = image_type(data)
        if validate_image and not extension:
            raise InvalidImageError()
        return DownloadedImage(data, extension, headers.get("content-type", ""))
    except ImageDownloadError:
        raise
    except UnacceptableAddressException as exc:
        raise LocalAddressError() from exc
    except (requests.RequestException, socket.gaierror, OSError) as exc:
        raise ImageDownloadError() from exc
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
