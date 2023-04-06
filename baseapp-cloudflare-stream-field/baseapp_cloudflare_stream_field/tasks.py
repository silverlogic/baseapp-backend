from celery import shared_task
from cloudflare_stream_field.stream import StreamClient

stream_client = StreamClient()


@shared_task
def refresh_from_cloudflare(content_type_pk, object_pk, attname, retries=1):
    from django.contrib.contenttypes.models import ContentType

    content_type = ContentType.objects.get(pk=content_type_pk)
    obj = content_type.get_object_for_this_type(pk=object_pk)
    cloudflare_video = getattr(obj, attname)
    if "uid" in cloudflare_video and cloudflare_video["status"]["state"] != "ready":
        new_value = stream_client.get_video_data(cloudflare_video["uid"])
        if new_value["status"]["state"] == "ready":
            setattr(obj, attname, new_value)
            obj.save(update_fields=[attname])
        elif retries < 1000:
            refresh_from_cloudflare.apply_async(
                kwargs={
                    "content_type_pk": content_type_pk,
                    "object_pk": object_pk,
                    "attname": attname,
                    "retries": retries + 1,
                },
                countdown=20 * retries,
            )


@shared_task
def generate_download_url(content_type_pk, object_pk, attname):
    from django.contrib.contenttypes.models import ContentType

    content_type = ContentType.objects.get(pk=content_type_pk)
    obj = content_type.get_object_for_this_type(pk=object_pk)
    cloudflare_video = getattr(obj, attname)

    if "uid" in cloudflare_video and "download_url" not in cloudflare_video["meta"]:
        response = stream_client.download_video(cloudflare_video["uid"])
        download_url = response["result"]["default"]["url"]
        cloudflare_video["meta"]["download_url"] = download_url
        stream_client.update_video_data(cloudflare_video["uid"], cloudflare_video["meta"])
        setattr(obj, attname, cloudflare_video)
        obj.save(update_fields=[attname])
