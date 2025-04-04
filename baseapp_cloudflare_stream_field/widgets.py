import json

from django.conf import settings
from django.forms import CheckboxInput, ClearableFileInput, forms
from django.templatetags.static import static

from baseapp_cloudflare_stream_field.stream import StreamClient


class CloudflareStreamAdminWidget(ClearableFileInput):
    template_name = "baseapp_cloudflare_stream_field/admin_async_file_input.html"

    def format_value(self, value):
        self.full_value = {}
        if value and isinstance(value, str):
            value = json.loads(value)
        if value and isinstance(value, dict):
            self.full_value = value
            return value["uid"]

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if self.full_value:
            uid = self.full_value.get("uid")
            context["widget"].update(
                {
                    "id": attrs["id"],
                    "preview": self.full_value.get("preview"),
                    "iframe": self.full_value.get("preview").replace("/watch", "/iframe"),
                    "dashboard": f"https://dash.cloudflare.com/{settings.CLOUDFLARE_ACCOUNT_ID}/stream/videos/{uid}",
                    "analytics": f"https://dash.cloudflare.com/{settings.CLOUDFLARE_ACCOUNT_ID}/stream/analytics?uid={uid}&time-window=43200",
                }
            )
        return context

    def value_from_datadict(self, data, files, name):
        if not self.is_required and CheckboxInput().value_from_datadict(
            data, files, self.clear_checkbox_name(name)
        ):
            return ""

        file_value = files.get(name)
        if not file_value:
            video_uid = data.get(name)
            if video_uid:
                stream_client = StreamClient()
                return stream_client.get_video_data(video_uid)

        return file_value or ""

    @property
    def media(self):
        js = ["tus.js", "baseapp_cloudflare_stream_field.js"]
        return forms.Media(
            js=[static("baseapp_cloudflare_stream_field/js/%s" % path) for path in js]
        )
