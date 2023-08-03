from django.contrib import admin
from nested_admin.nested import NestedTabularInline

from .models import Attachment, EmailTemplate


class AttachmentsInline(NestedTabularInline):
    model = Attachment
    fields = ("filename", "file")
    show_change_link = True
    extra = 1


class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    inlines = [AttachmentsInline]
    readonly_fields = ("raw_html",)
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


admin.site.register(EmailTemplate, EmailTemplateAdmin)
