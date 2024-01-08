from django.contrib import admin
from nested_admin.nested import NestedTabularInline

from .models import Attachment, EmailTemplate, SmsTemplate


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


class SmsTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "message")
    search_fields = ("name", "message")
    ordering = ("-id",)


admin.site.register(EmailTemplate, EmailTemplateAdmin)
admin.site.register(SmsTemplate, SmsTemplateAdmin)
