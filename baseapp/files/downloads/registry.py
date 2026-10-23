"""
The registry of protected model file fields.

A registered field is served through the protected download endpoints, which check the
viewer's access on every request, and the clients get no storage URL from them. Registering
does not change the field's storage: keep it on private storage (system check
``baseapp_files.W010``) and do not expose the raw field elsewhere (object types,
serializers, the admin). Register fields from ``AppConfig.ready()``:

    from baseapp.files.downloads import protected_files

    protected_files.register(Invoice, "pdf", filename=lambda invoice: f"{invoice.number}.pdf")
"""

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Literal, Optional, Union

from django.apps import apps
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError
from django.core.files import File as DjangoFile
from django.db import models
from django.db.models.fields.files import FieldFile
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import APIException, NotAuthenticated, PermissionDenied

from ..content_safety import allowed_content_type
from .responses import DEFAULT_CACHE_CONTROL, safe_filename

Disposition = Literal["attachment", "inline"]
EnsureResult = Union[FieldFile, DjangoFile, bytes, None]
UserType = Any

KEY_PATTERN = re.compile(r"^[\w.-]+$")
# `t/<ticket>` is the ticket endpoint, so `t` cannot be a key.
RESERVED_KEYS = frozenset({"t"})
DISPOSITIONS = ("attachment", "inline")
FALLBACK_CONTENT_TYPE = "application/octet-stream"


@dataclass(frozen=True)
class ProtectedFileSpec:
    """How one registered file field is protected and served. Built by ``register``."""

    key: str
    model: type[models.Model]
    field: str
    permission: Union[str, Literal[False]]
    check: Optional[Callable[[UserType, models.Model], None]]
    queryset: Optional[Callable[[UserType], models.QuerySet]]
    lookup_field: str
    filename: Union[str, Callable[[models.Model], str], None]
    content_type: Union[str, Callable[[models.Model], str], None]
    disposition: Disposition
    csp: Optional[str]
    ensure: Optional[Callable[[models.Model], EnsureResult]]
    cache_control: str

    def get_queryset(self, user: UserType) -> models.QuerySet:
        """The objects ``user`` may address at all; others answer 404 rather than 403."""
        if self.queryset is not None:
            return self.queryset(user)
        return self.model._default_manager.all()

    def uses_public_id(self) -> bool:
        """``lookup_field="public_id"`` on a ``DocumentIdMixin`` model, whose public id is not a column."""
        return self.lookup_field == "public_id" and hasattr(self.model, "get_by_public_id")

    def get_object(self, user: UserType, object_id: Any) -> Optional[models.Model]:
        """The object ``object_id`` names among those ``user`` may address, or None."""
        queryset = self.get_queryset(user)
        try:
            if self.uses_public_id():
                target = self.model.get_by_public_id(object_id)
                if not isinstance(target, self.model):  # unknown id, or another model's
                    return None
                return queryset.filter(pk=target.pk).first()
            return queryset.filter(**{self.lookup_field: object_id}).first()
        except (ObjectDoesNotExist, ValueError, TypeError, ValidationError):
            return None

    def get_field_file(self, obj: models.Model) -> FieldFile:
        return getattr(obj, self.field)

    def get_lookup_value(self, obj: models.Model) -> str:
        """The ``objectId`` clients use for ``obj``: its ``lookup_field`` value."""
        return str(getattr(obj, self.lookup_field))

    def is_empty(self, obj: models.Model) -> bool:
        """Nothing to serve: no stored file and no ``ensure`` to derive one."""
        return not self.get_field_file(obj) and self.ensure is None

    def get_filename(self, obj: models.Model) -> str:
        """The download name: ``filename`` (a callable or a literal), else the stored base name."""
        if callable(self.filename):
            name = self.filename(obj)
        elif self.filename:
            name = self.filename
        else:
            name = self.get_field_file(obj).name or ""
        return safe_filename(name)

    def get_content_type(self, obj: models.Model, filename: Optional[str] = None) -> str:
        """``content_type`` (a callable or a literal), else the allowlisted type of the name."""
        if callable(self.content_type):
            content_type = self.content_type(obj)
        else:
            content_type = self.content_type
        if not content_type:
            content_type = allowed_content_type(filename or self.get_filename(obj))
        return content_type or FALLBACK_CONTENT_TYPE

    def check_access(self, user: UserType, obj: models.Model) -> None:
        """
        Raise unless ``user`` may download ``obj``'s file: ``permission`` first, then
        ``check``, whose own exceptions (coded ``PermissionDenied``, ``Gone``...) pass through.

        Raises:
            NotAuthenticated: anonymous caller without the permission.
            PermissionDenied: authenticated caller without the permission.
        """
        user = user or AnonymousUser()
        if self.permission and not user.has_perm(self.permission, obj):
            if not user.is_authenticated:
                raise NotAuthenticated()
            raise PermissionDenied(_("You don't have permission to download this file."))
        if self.check is not None:
            self.check(user, obj)

    def is_accessible(self, user: UserType, obj: models.Model) -> bool:
        """``check_access`` as a boolean, for fields that render null instead of failing."""
        try:
            self.check_access(user, obj)
        except (APIException, DjangoPermissionDenied, Http404):
            return False
        return True


class ProtectedFilesRegistry:
    """Registered ``ProtectedFileSpec`` objects, by key."""

    def __init__(self) -> None:
        self._specs: dict[str, ProtectedFileSpec] = {}

    def register(
        self,
        model: Union[type[models.Model], str],
        field: str,
        *,
        key: Optional[str] = None,
        permission: Union[str, Literal[False], None] = None,
        check: Optional[Callable[[UserType, models.Model], None]] = None,
        queryset: Optional[Callable[[UserType], models.QuerySet]] = None,
        lookup_field: str = "pk",
        filename: Union[str, Callable[[models.Model], str], None] = None,
        content_type: Union[str, Callable[[models.Model], str], None] = None,
        disposition: Disposition = "attachment",
        csp: Optional[str] = None,
        ensure: Optional[Callable[[models.Model], EnsureResult]] = None,
        cache_control: str = DEFAULT_CACHE_CONTROL,
    ) -> ProtectedFileSpec:
        """
        Protect ``model.field``. Call it from ``AppConfig.ready()``.

        Args:
            model: the model class, or its ``"app_label.ModelName"`` label.
            field: name of a ``FileField``/``ImageField`` on it.
            key: identifies the field in URLs and GraphQL (default ``"<app>.<model>.<field>"``).
            permission: checked as ``user.has_perm(permission, obj)`` (default
                ``"<app>.view_<model>"``, i.e. "may view the object", which backends may grant
                broadly); ``False`` skips it, leaving ``check``/``queryset``.
            check: ``callable(user, obj)`` run after the permission; it may raise DRF
                ``PermissionDenied``/``NotAuthenticated``/``NotFound`` (codes included) or ``Gone``.
            queryset: ``callable(user)`` scoping which objects exist for ``user`` (404 outside it).
            lookup_field: the field ``objectId`` matches (e.g. ``"public_id"``).
            filename: download name, a callable(obj) or a literal; default the stored base name.
            content_type: a callable(obj) or a literal; default the allowlisted type of the name.
            disposition: ``"attachment"`` (default) or ``"inline"``. Inline is honoured only for
                types browsers display safely, or when a ``csp`` is given.
            csp: Content-Security-Policy for inline responses (default ``"sandbox; default-src 'none'"``).
            ensure: ``callable(obj)`` returning a ``FieldFile``, file or bytes when the stored file
                is missing, to regenerate or derive it (``None``: 404).
            cache_control: the ``Cache-Control`` header (default ``"private, no-store"``).
        """
        if isinstance(model, str):
            model = apps.get_model(model)
        key = key or f"{model._meta.app_label}.{model._meta.model_name}.{field}"
        if not KEY_PATTERN.match(key) or key in RESERVED_KEYS:
            raise ImproperlyConfigured(
                f"Invalid protected file key {key!r}: use letters, digits, '_', '.' and '-' "
                f"(and not {', '.join(sorted(RESERVED_KEYS))})."
            )
        if key in self._specs:
            raise ImproperlyConfigured(f"A protected file is already registered as {key!r}.")
        if disposition not in DISPOSITIONS:
            raise ImproperlyConfigured(
                f"Protected file {key!r}: disposition must be one of {DISPOSITIONS}."
            )
        if permission is None:
            permission = f"{model._meta.app_label}.view_{model._meta.model_name}"

        spec = ProtectedFileSpec(
            key=key,
            model=model,
            field=field,
            permission=permission,
            check=check,
            queryset=queryset,
            lookup_field=lookup_field,
            filename=filename,
            content_type=content_type,
            disposition=disposition,
            csp=csp,
            ensure=ensure,
            cache_control=cache_control,
        )
        self._specs[key] = spec
        return spec

    def unregister(self, key: str) -> None:
        """Remove a registration (mainly for tests)."""
        self._specs.pop(key, None)

    def get(self, key: str) -> Optional[ProtectedFileSpec]:
        return self._specs.get(key)

    def get_for(self, model_or_obj: Any, field: str) -> Optional[ProtectedFileSpec]:
        """The spec registered for ``field`` on this model (or a parent of it), if any."""
        model = model_or_obj if isinstance(model_or_obj, type) else type(model_or_obj)
        for spec in self._specs.values():
            if spec.field == field and issubclass(model, spec.model):
                return spec
        return None

    def __iter__(self) -> Iterator[ProtectedFileSpec]:
        return iter(list(self._specs.values()))

    def __contains__(self, key: object) -> bool:
        return key in self._specs

    def __len__(self) -> int:
        return len(self._specs)


protected_files = ProtectedFilesRegistry()
