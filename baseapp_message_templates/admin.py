from typing import Any

from django import forms
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _
from nested_admin.nested import NestedTabularInline

from .models import Attachment, EmailTemplate, SmsTemplate

try:
    from ckeditor.widgets import CKEditorWidget
except ImportError:  # pragma: no cover - optional dependency
    CKEditorWidget = None


class AttachmentsInline(NestedTabularInline):
    model = Attachment
    fields = ("filename", "file")
    show_change_link = True
    extra = 1


class EmailTemplateAdminForm(forms.ModelForm):
    class Meta:
        model = EmailTemplate
        fields = "__all__"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        editor = getattr(settings, "MESSAGE_TEMPLATES_EDITOR", "prose")
        if editor == "ckeditor":
            if CKEditorWidget is None:
                raise ImproperlyConfigured(
                    _(
                        "MESSAGE_TEMPLATES_EDITOR is set to 'ckeditor' but "
                        "django-ckeditor is not installed."
                    )
                )
            self.fields["html_content"].widget = CKEditorWidget()
            self.fields["plain_text_content"].widget = CKEditorWidget()


EDITOR = getattr(settings, "MESSAGE_TEMPLATES_EDITOR", "prose")


class EmailTemplateAdmin(admin.ModelAdmin):
    form = EmailTemplateAdminForm
    list_display = ("id", "name")
    inlines = [AttachmentsInline]
    readonly_fields = ("raw_html",)
    change_form_template = (
        "admin/baseapp_message_templates/emailtemplate/change_form.html"
        if EDITOR == "prose"
        else None
    )
    fieldsets = (
        (
            None,
            {"fields": ("name",)},
        ),
        (
            "SendGrid",
            {"fields": ("sendgrid_template_id",)},
        ),
        (
            "Core",
            {
                "fields": (
                    "subject",
                    "html_content",
                    "raw_html",
                    "plain_text_content",
                )
            },
        ),
    )

    def raw_html(self, obj):
        return obj.html_content


class SmsTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "message")
    search_fields = ("name", "message")
    ordering = ("-id",)


admin.site.register(EmailTemplate, EmailTemplateAdmin)
admin.site.register(SmsTemplate, SmsTemplateAdmin)
