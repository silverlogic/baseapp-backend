from functools import partial
from typing import Any

import swapper
from django.contrib import admin
from django.contrib.admin.checks import InlineModelAdminChecks
from django.contrib.admin.utils import flatten_fieldsets
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model, QuerySet
from django.forms import BaseModelFormSet, modelformset_factory
from django.http import HttpRequest
from django.template.defaultfilters import filesizeformat
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from baseapp_core.admin_helpers import ModelAdmin, TabularInline
from baseapp_core.plugins import apply_if_installed

File = swapper.load_model("baseapp_files", "File")
FileTarget = swapper.load_model("baseapp_files", "FileTarget")


@admin.register(File)
class FileAdmin(ModelAdmin):
    list_display = ("pk", "name", "file_content_type", "parent", "created_by", "created")
    list_filter = ("created", "upload_status", "file_content_type")
    list_select_related = ("parent__content_type", "created_by")
    search_fields = ("name", "description")
    # Autocomplete instead of <select>: `parent` points at the global DocumentId registry,
    # and rendering every row as an option made the change form unusable. `profile` (the
    # profile that created the file) only exists when baseapp_profiles is installed.
    autocomplete_fields = (
        "parent",
        "created_by",
        *apply_if_installed("baseapp_profiles", ["profile"]),
    )


@admin.register(FileTarget)
class FileTargetAdmin(ModelAdmin):
    list_display = (
        "pk",
        "target",
        "is_files_enabled",
        "files_count",
    )
    list_filter = ("is_files_enabled",)
    list_select_related = ("target__content_type",)
    search_fields = ("target_id",)
    autocomplete_fields = ("target",)


def file_link(file_obj: "File", label: str | None = None) -> str:
    """
    A link that opens the stored file, labelled with `label` or the file's name; "-" while
    nothing is stored. Private storage signs the link, so it expires.
    """
    if not file_obj.file:
        return "-"
    return format_html(
        '<a href="{}" target="_blank" rel="noopener">{}</a>',
        file_obj.file.url,
        label or str(file_obj),
    )


class FilesInlineFormSet(BaseModelFormSet):
    """
    The files attached to the object being edited.

    A file points at its object through `parent`, a `DocumentId`, rather than a foreign key,
    so the files are found the way `FileableModel.files` finds them.
    """

    def __init__(
        self,
        data: Any = None,
        files: Any = None,
        instance: Model | None = None,
        save_as_new: bool = False,
        prefix: str | None = None,
        queryset: QuerySet | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Narrow `queryset` (the inline's, or every file) to the files whose parent is
        `instance`; an object not yet saved has none.
        """
        self.instance = instance
        self.save_as_new = save_as_new
        if queryset is None:
            queryset = self.model._default_manager.all()
        if instance is None or instance.pk is None:
            queryset = queryset.none()
        else:
            queryset = queryset.filter(
                parent__content_type=ContentType.objects.get_for_model(instance),
                parent__object_id=instance.pk,
            )
        super().__init__(data, files, prefix=prefix, queryset=queryset, **kwargs)

    @classmethod
    def get_default_prefix(cls) -> str:
        return "attached-files"


class FilesInlineChecks(InlineModelAdminChecks):
    """An inline's checks, less the foreign key to the parent model that files do not have."""

    def _check_exclude_of_parent_model(self, obj: Any, parent_model: type[Model]) -> list:
        return []

    def _check_relation(self, obj: Any, parent_model: type[Model]) -> list:
        return []


class FilesInline(TabularInline):
    """
    The files attached to an object, on that object's change page.

    Add it to the `inlines` of any model's admin; files are attached through `DocumentId`, so
    the model needs no foreign key to `File`. Read-only: files arrive through the upload API
    and are attached there, so the inline lists them, in every upload state, with a link to
    each, and changes nothing. Each row's title links to the file's own admin page.
    """

    model = File
    formset = FilesInlineFormSet
    checks_class = FilesInlineChecks
    fields = (
        "download",
        "file_content_type",
        "size",
        "upload_status",
        "created_by",
        "created",
    )
    readonly_fields = fields
    ordering = ("-created",)
    extra = 0
    can_delete = False
    show_change_link = True
    verbose_name = _("attached file")
    verbose_name_plural = _("attached files")

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).select_related("created_by")

    def has_add_permission(self, request: HttpRequest, obj: Model | None = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Model | None = None) -> bool:
        return False

    def get_formset(self, request: HttpRequest, obj: Model | None = None, **kwargs: Any) -> type:
        """
        `InlineModelAdmin.get_formset`, building a model formset instead of an inline one.

        Keeps Django's guard against a POST changing what the user may not change, and builds
        the formset edit-only, so no file can be created through the inline whatever is posted.
        """
        fields = kwargs.pop("fields", None) or flatten_fieldsets(self.get_fieldsets(request, obj))
        readonly = self.get_readonly_fields(request, obj)
        can_add = self.has_add_permission(request, obj)
        can_change = self.has_change_permission(request, obj)

        class PermissionProtectedModelForm(self.form):
            def has_changed(self) -> bool:
                if self.instance._state.adding:
                    return can_add and super().has_changed()
                return can_change and super().has_changed()

        return modelformset_factory(
            self.model,
            **{
                "edit_only": True,
                "form": PermissionProtectedModelForm,
                "formfield_callback": partial(self.formfield_for_dbfield, request=request),
                "formset": self.formset,
                "extra": self.get_extra(request, obj),
                "can_delete": self.can_delete and self.has_delete_permission(request, obj),
                "can_order": False,
                "fields": [field for field in fields if field not in readonly],
                "min_num": self.get_min_num(request, obj),
                "max_num": self.get_max_num(request, obj),
                **kwargs,
            },
        )

    @admin.display(description=_("file"))
    def download(self, obj: "File") -> str:
        return file_link(obj, _("Open"))

    @admin.display(description=_("size"))
    def size(self, obj: "File") -> str:
        return filesizeformat(obj.file_size) if obj.file_size is not None else "-"
