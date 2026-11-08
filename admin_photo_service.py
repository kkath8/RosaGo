"""Server-only destination Storage writes, after fresh Admin authorization."""
from dataclasses import dataclass
from io import BytesIO
import os
import re
from urllib.parse import urlsplit
from uuid import uuid4
import warnings

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError
from storage3 import SyncStorageClient
from storage3.exceptions import StorageException

from admin_authorization_service import is_current_admin, AdminAuthorizationError
from admin_places_service import _context

MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTO_PIXELS = 20_000_000
FORMATS = {'JPEG': ('image/jpeg', 'jpg'), 'PNG': ('image/png', 'png'), 'WEBP': ('image/webp', 'webp')}
_http_client = httpx.Client  # Operation-owned factory; injectable for offline transport tests.


class PhotoError(Exception):
    status = 503


class PhotoValidationError(PhotoError):
    status = 400


class PhotoAccessError(PhotoError):
    status = 403


@dataclass(frozen=True, repr=False)
class PreparedPhoto:
    content: bytes
    content_type: str
    extension: str


def photo_location():
    """Public URL configuration only; never return the Storage secret."""
    base = os.getenv('SUPABASE_URL', '').rstrip('/')
    bucket = os.getenv('SUPABASE_STORAGE_BUCKET', '')
    parsed = urlsplit(base)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path
            or bucket != 'destination-images'):
        raise PhotoError('Photo upload is temporarily unavailable.')
    return base, bucket


def valid_photo_url(value):
    if type(value) is not str:
        return False
    try:
        base, bucket = photo_location()
    except PhotoError:
        return False
    prefix = f'{base}/storage/v1/object/public/{bucket}/'
    return value.startswith(prefix) and bool(re.fullmatch(r'destinations/[0-9a-f]{32}\.(?:jpg|png|webp)', value[len(prefix):]))


def prepare_photo(file):
    """Decode and re-encode actual image pixels; discard metadata and trailing data."""
    extension = (file.filename or '').rsplit('.', 1)[-1].lower()
    if extension not in ('jpg', 'jpeg', 'png', 'webp'):
        raise PhotoValidationError('Choose a JPG, PNG, or WebP photo.')
    raw = file.stream.read(MAX_PHOTO_BYTES + 1)
    if not raw or len(raw) > MAX_PHOTO_BYTES:
        raise PhotoValidationError('Choose a non-empty photo no larger than 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                fmt = image.format
                if (fmt not in FORMATS or file.mimetype != FORMATS[fmt][0]
                        or extension not in ({'jpg', 'jpeg'} if fmt == 'JPEG' else {FORMATS[fmt][1]})
                        or image.width * image.height > MAX_PHOTO_PIXELS
                        or image.width > 8192 or image.height > 8192
                        or getattr(image, 'n_frames', 1) != 1):
                    raise ValueError()
                image.verify()
            with Image.open(BytesIO(raw)) as image:
                oriented = ImageOps.exif_transpose(image)
                pixels = oriented.convert('RGB' if fmt == 'JPEG' else 'RGBA')
                clean = Image.new(pixels.mode, pixels.size)
                clean.paste(pixels)
                output = BytesIO()
                clean.save(output, format=fmt, **({'quality': 85} if fmt in ('JPEG', 'WEBP') else {}))
                content = output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise PhotoValidationError('This file is not a supported, valid still photo. Use JPG, PNG, or WebP up to 20 megapixels.') from None
    if len(content) > MAX_PHOTO_BYTES:
        raise PhotoValidationError('The processed photo exceeds 5 MB. Choose a smaller image.')
    return PreparedPhoto(content, *FORMATS[fmt])


def photo_object_path(extension, planned_object_id=None):
    """Optional operator-reserved identity; never a browser-supplied path."""
    if extension not in ('jpg','png','webp') or (planned_object_id is not None and
            (type(planned_object_id) is not str or not re.fullmatch(r'[0-9a-f]{32}',planned_object_id))):
        raise PhotoValidationError('Invalid reserved photo identity.')
    return f'destinations/{planned_object_id if planned_object_id is not None else uuid4().hex}.{extension}'


def upload_photo(context, photo, *, planned_object_id=None):
    """Only Storage uses the dedicated secret. Database writes use caller authority."""
    _context(context)
    try:
        allowed = is_current_admin(context)
    except AdminAuthorizationError:
        raise PhotoError('Photo upload authorization is temporarily unavailable.') from None
    if not allowed:
        raise PhotoAccessError('Admin access required.')
    base, bucket = photo_location()
    secret = os.getenv('SUPABASE_STORAGE_SECRET_KEY', '')
    # The configured modern secret is an API key, not a bearer JWT. storage3
    # accepts explicit headers, so no Auth client/session ever receives it.
    if not re.fullmatch(r'sb_secret_[A-Za-z0-9_-]+', secret):
        raise PhotoError('Photo upload is temporarily unavailable.')
    path = photo_object_path(photo.extension,planned_object_id)
    try:
        with _http_client(timeout=30, follow_redirects=False, trust_env=False) as http:
            storage = SyncStorageClient(base + '/storage/v1/', {'apikey': secret}, http_client=http)
            storage.from_(bucket).upload(path, photo.content,
                {'content-type': photo.content_type, 'upsert': 'false', 'cache-control': '31536000'})
    except (StorageException, httpx.HTTPError, ValueError, KeyError, TypeError):
        raise PhotoError('The photo could not be uploaded. Your destination has not been saved. Please try again.') from None
    return f'{base}/storage/v1/object/public/{bucket}/{path}'
