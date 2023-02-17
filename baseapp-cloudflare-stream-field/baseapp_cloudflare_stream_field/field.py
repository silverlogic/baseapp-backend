import json

from django.db.models import JSONField, signals
from django.db.models.query_utils import DeferredAttribute

from cloudflare_stream_field.stream import StreamClient
from cloudflare_stream_field.tasks import refresh_from_cloudflare
from cloudflare_stream_field.widgets import CloudflareStreamAdminWidget

stream_client = StreamClient()


class CloudflareStreamDeferredAttribute(DeferredAttribute):
    def __set__(self, instance, value):
        # Check if its an video ID, seems like its a 32char hexdecimal value.
        # But was afraid of them changing this structure in the future, trying to make it more future proof:
        if value and isinstance(value, str) and len(value) >= 16 and len(value) <= 64:
            value = stream_client.get_video_data(value)
        instance.__dict__[self.field.attname] = value


class CloudflareStreamField(JSONField):
    descriptor_class = CloudflareStreamDeferredAttribute

    def contribute_to_class(self, cls, name, **kwargs):
        super().contribute_to_class(cls, name, **kwargs)
        if not cls._meta.abstract:
            signals.pre_delete.connect(self.delete_from_cloudflare, sender=cls)
            signals.post_save.connect(self.refresh_from_cloudflare, sender=cls)

    def delete_from_cloudflare(self, sender, instance, **kwargs):
        cloudflare_video = getattr(instance, self.attname)
        if cloudflare_video and "uid" in cloudflare_video:
            if isinstance(cloudflare_video, str):
                cloudflare_video = json.loads(cloudflare_video)
            uid = cloudflare_video["uid"]
            stream_client.delete_video_data(uid)

    def refresh_from_cloudflare(self, sender, instance, **kwargs):
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(sender)
        refresh_from_cloudflare.apply_async(
            kwargs={
                "content_type_pk": content_type.pk,
                "object_pk": instance.pk,
                "attname": self.attname,
            },
            countdown=5,
        )

    def formfield(self, *args, **kwargs):
        kwargs.update(
            {
                "max_length": self.max_length,
                "widget": CloudflareStreamAdminWidget,
            }
        )
        return super().formfield(*args, **kwargs)
