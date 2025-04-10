import json

from django import forms
from django.db.models import JSONField, signals
from django.db.models.query_utils import DeferredAttribute

from baseapp_cloudflare_stream_field.stream import StreamClient
from baseapp_cloudflare_stream_field.tasks import (
    generate_download_url,
    refresh_from_cloudflare,
)
from baseapp_cloudflare_stream_field.widgets import CloudflareStreamAdminWidget

stream_client = StreamClient()


class CloudflareFormJSONField(forms.JSONField):
    def bound_data(self, data, initial):
        if data and isinstance(data, dict):
            return data
        return super().bound_data(data, initial)


class CloudflareStreamDeferredAttribute(DeferredAttribute):
    def __set__(self, instance, value):
        # Check if its an video ID, seems like its a 32char hexdecimal value.
        # But was afraid of them changing this structure in the future, trying to make it more future proof:
        if value and isinstance(value, str) and len(value) >= 16 and len(value) <= 64:
            value = stream_client.get_video_data(value)

        instance.__dict__[self.field.attname] = value


class CloudflareStreamField(JSONField):
    descriptor_class = CloudflareStreamDeferredAttribute

    def __init__(
        self,
        downloadable=False,
        **kwargs,
    ):
        self.downloadable = downloadable
        super().__init__(**kwargs)

    def contribute_to_class(self, cls, name, **kwargs):
        super().contribute_to_class(cls, name, **kwargs)
        if not cls._meta.abstract:
            signals.pre_delete.connect(self.pre_delete, sender=cls)
            signals.post_save.connect(self.post_save, sender=cls)

    def pre_delete(self, sender, instance, **kwargs):
        cloudflare_video = getattr(instance, self.attname)
        if cloudflare_video and "uid" in cloudflare_video:
            if isinstance(cloudflare_video, str):
                cloudflare_video = json.loads(cloudflare_video)
            uid = cloudflare_video["uid"]
            stream_client.delete_video_data(uid)

    def post_save(self, sender, instance, **kwargs):
        cloudflare_video = getattr(instance, self.attname)
        if cloudflare_video and "uid" in cloudflare_video:
            from django.contrib.contenttypes.models import ContentType

            content_type = ContentType.objects.get_for_model(sender)

            if cloudflare_video["status"]["state"] != "ready":
                refresh_from_cloudflare.apply_async(
                    kwargs={
                        "content_type_pk": content_type.pk,
                        "object_pk": instance.pk,
                        "attname": self.attname,
                    },
                    countdown=5,
                )

            if self.downloadable and "download_url" not in cloudflare_video["meta"]:
                generate_download_url.apply_async(
                    kwargs={
                        "content_type_pk": content_type.pk,
                        "object_pk": instance.pk,
                        "attname": self.attname,
                    }
                )

    def formfield(self, *args, **kwargs):
        kwargs.update(
            {
                "form_class": CloudflareFormJSONField,
                "max_length": self.max_length,
                "widget": CloudflareStreamAdminWidget,
            }
        )
        return super().formfield(*args, **kwargs)

    def bound_data(self, data, initial):
        if data and isinstance(data, dict):
            return data
        return super().bound_data(data, initial)
