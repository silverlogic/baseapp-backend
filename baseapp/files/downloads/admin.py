from typing import Any, Callable, Optional

from django.core.files.storage import Storage
from django.db import models
from django.http import HttpRequest
from django.utils.html import format_html

from ..storage import files_storage_is_private
from ..storage.alias import AliasStorage
from .registry import protected_files
from .services import download_path

LINK_SUFFIX = "_link"


class ProtectedFileAdminMixin:
    """
    Shows the private file fields of a ``ModelAdmin`` as read-only ``<field>_link`` entries
    instead of their upload widget, which would print the storage URL:

    - a registered field links to the protected download (the admin session authenticates it);
    - another private field shows its name only;
    - public fields keep their widget.

    A field is private when its storage only signs URLs (S3 with ``querystring_auth``,
    ``SignedFileSystemStorage``) or is an ``AliasStorage`` named in ``private_storage_aliases``.

        class InvoiceAdmin(ProtectedFileAdminMixin, admin.ModelAdmin):
            private_storage_aliases = ("private",)
    """

    private_storage_aliases: tuple[str, ...] = ()

    def is_private_storage(self, storage: Storage) -> bool:
        if isinstance(storage, AliasStorage) and storage.alias in self.private_storage_aliases:
            return True
        return files_storage_is_private(storage)

    def get_protected_file_fields(self) -> list[str]:
        """Names of the model's file fields shown as links: registered or private ones."""
        names = []
        for field in self.model._meta.get_fields():  # type: ignore[attr-defined]
            if not isinstance(field, models.FileField):
                continue
            if protected_files.get_for(self.model, field.name) or self.is_private_storage(  # type: ignore[attr-defined]
                field.storage
            ):
                names.append(field.name)
        return names

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> list[str]:
        fields = list(super().get_readonly_fields(request, obj))  # type: ignore[misc]
        for name in self.get_protected_file_fields():
            if f"{name}{LINK_SUFFIX}" not in fields:
                fields.append(f"{name}{LINK_SUFFIX}")
        return fields

    def get_fields(self, request: HttpRequest, obj: Any = None) -> list[str]:
        hidden = set(self.get_protected_file_fields())
        fields = super().get_fields(request, obj)  # type: ignore[misc]
        return [name for name in fields if name not in hidden]

    def get_exclude(self, request: HttpRequest, obj: Any = None) -> list[str]:
        exclude = list(super().get_exclude(request, obj) or [])  # type: ignore[misc]
        return exclude + [name for name in self.get_protected_file_fields() if name not in exclude]

    def protected_file_link_url(self, obj: models.Model, field_name: str) -> Optional[str]:
        """Where ``field_name``'s link points; None shows the name only."""
        spec = protected_files.get_for(obj, field_name)
        return download_path(spec, obj) if spec else None

    def render_protected_file_link(self, obj: models.Model, field_name: str) -> str:
        value = getattr(obj, field_name, None)
        if not value:
            return "-"
        url = self.protected_file_link_url(obj, field_name)
        if url is None:
            return value.name
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>', url, value.name
        )

    def __getattr__(self, name: str) -> Callable[[models.Model], str]:
        # `<field>_link` read-only entries, resolved like admin methods.
        if name.endswith(LINK_SUFFIX) and not name.startswith("_"):
            field_name = name[: -len(LINK_SUFFIX)]

            def link(obj: models.Model) -> str:
                return self.render_protected_file_link(obj, field_name)

            link.short_description = field_name.replace("_", " ")  # type: ignore[attr-defined]
            return link
        raise AttributeError(name)
