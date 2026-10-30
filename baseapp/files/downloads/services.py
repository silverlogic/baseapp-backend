"""Loading, checking and serving a protected file; shared by the views, GraphQL and DRF."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cached_property
from typing import Any, Literal, Optional

from django.conf import settings
from django.core.files import File as DjangoFile
from django.db import models
from django.db.models.fields.files import FieldFile
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import NotFound

from .registry import ProtectedFileSpec, UserType
from .responses import Content, protected_file_response
from .signals import protected_file_downloaded

DEFAULT_DOWNLOADS_URL = "/v1/files/protected/"


def _size_errors() -> tuple[type[Exception], ...]:
    """What reading a missing file's size raises: OSError locally, ClientError on S3."""
    try:
        from botocore.exceptions import ClientError
    except ImportError:
        return (OSError, ValueError)
    return (OSError, ValueError, ClientError)


SIZE_ERRORS = _size_errors()


def protected_downloads_url() -> str:
    """Where ``baseapp.files.downloads.urls`` is mounted (``BASEAPP_FILES_PROTECTED_DOWNLOADS_URL``)."""
    url = getattr(settings, "BASEAPP_FILES_PROTECTED_DOWNLOADS_URL", DEFAULT_DOWNLOADS_URL)
    return url if url.endswith("/") else f"{url}/"


def download_path(spec: ProtectedFileSpec, obj: models.Model) -> str:
    """The authenticated download path of ``obj``'s file (checked against the session/JWT)."""
    return f"{protected_downloads_url()}{spec.key}/{spec.get_lookup_value(obj)}"


def ticket_path(ticket: str) -> str:
    """The download-link path for a ticket."""
    return f"{protected_downloads_url()}t/{ticket}"


def get_protected_object(spec: ProtectedFileSpec, user: UserType, object_id: Any) -> models.Model:
    """
    Load the object ``object_id`` names and check ``user`` may download its file.

    Raises:
        NotFound: no such object within ``spec.queryset(user)``.
        NotAuthenticated / PermissionDenied: no permission.
        Whatever ``spec.check`` raises.
    """
    obj = spec.get_object(user, object_id)
    if obj is None:
        raise NotFound(_("File not found."))
    spec.check_access(user, obj)
    return obj


def is_stored(field_file: FieldFile) -> bool:
    """Whether the field holds a name and its storage has that file."""
    return bool(field_file) and field_file.storage.exists(field_file.name)


def get_protected_content(spec: ProtectedFileSpec, obj: models.Model) -> Content:
    """
    The content to serve: the stored file, else what ``spec.ensure`` regenerates or derives.

    Raises:
        NotFound: nothing stored and nothing derived.
    """
    field_file = spec.get_field_file(obj)
    if is_stored(field_file):
        return field_file
    if spec.ensure is not None:
        content = spec.ensure(obj)
        if isinstance(content, (bytes, bytearray)):
            return bytes(content)
        if isinstance(content, FieldFile):
            if is_stored(content):
                return content
        elif isinstance(content, DjangoFile):
            return content
    raise NotFound(_("File not found."))


def serve_protected_file(
    spec: ProtectedFileSpec,
    obj: models.Model,
    request: HttpRequest,
    user: UserType,
    via: Literal["session", "ticket"],
) -> HttpResponse:
    """Build the response for an object whose access was checked, and send the signal."""
    response = protected_file_response(spec, obj, get_protected_content(spec, obj), request)
    protected_file_downloaded.send(
        sender=spec.model,
        instance=obj,
        field=spec.field,
        key=spec.key,
        user=user,
        request=request,
        via=via,
    )
    return response


@dataclass
class ProtectedFileInfo:
    """
    What clients get to know about a protected file (GraphQL ``ProtectedFile``, the DRF
    field): never a URL, which they mint with ``protectedFileLink``.
    """

    spec: ProtectedFileSpec
    obj: models.Model
    key: str = field(init=False)
    object_id: str = field(init=False)

    def __post_init__(self) -> None:
        self.key = self.spec.key
        self.object_id = self.spec.get_lookup_value(self.obj)

    @cached_property
    def file_name(self) -> str:
        return self.spec.get_filename(self.obj)

    @cached_property
    def content_type(self) -> str:
        return self.spec.get_content_type(self.obj, self.file_name)

    @cached_property
    def size(self) -> Optional[int]:
        """The stored size, or None when unknown (derived content, missing file)."""
        field_file = self.spec.get_field_file(self.obj)
        if not field_file:
            return None
        try:
            return field_file.size
        except SIZE_ERRORS:
            return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "object_id": self.object_id,
            "file_name": self.file_name,
            "content_type": self.content_type,
            "size": self.size,
        }


def describe_protected_file(
    spec: Optional[ProtectedFileSpec], obj: Optional[models.Model], user: UserType
) -> Optional[ProtectedFileInfo]:
    """The file's description for ``user``, or None when there is no file or no access."""
    if spec is None or obj is None or spec.is_empty(obj) or not spec.is_accessible(user, obj):
        return None
    return ProtectedFileInfo(spec, obj)


def link_expires_at(max_age: int) -> datetime:
    return timezone.now() + timedelta(seconds=max_age)
