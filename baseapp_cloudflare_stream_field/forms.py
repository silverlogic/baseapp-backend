from django.core.exceptions import ValidationError
from django.forms import fields

from baseapp_cloudflare_stream_field.widgets import CloudflareStreamAdminWidget


class FormCloudflareStreamFileField(fields.FileField):
    widget = CloudflareStreamAdminWidget

    def to_python(self, data):
        if self.required:
            if not data or data == "None":
                raise ValidationError(self.error_messages["empty"])
        return data
