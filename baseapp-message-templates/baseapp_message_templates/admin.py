from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from nested_admin.nested import NestedTabularInline

from .models import Attachment, EmailTemplate, SmsTemplate, TemplateTranslation


class AttachmentsInline(NestedTabularInline):
    model = Attachment
    fields = ("filename", "file")
    show_change_link = True
    extra = 1


class TemplateTranslationAdminInline(GenericTabularInline):
    model = TemplateTranslation
    extra = 0
    ct_field = "target_content_type"
    ct_fk_field = "target_object_id"


class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    inlines = [AttachmentsInline, TemplateTranslationAdminInline]
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
    )

    def raw_html(self, obj):
        return obj.html_content


class SmsTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "message")
    search_fields = ("name", "message")
    ordering = ("-id",)


admin.site.register(EmailTemplate, EmailTemplateAdmin)
admin.site.register(SmsTemplate, SmsTemplateAdmin)
