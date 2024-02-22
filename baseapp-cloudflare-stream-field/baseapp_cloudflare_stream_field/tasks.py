from celery import shared_task
from django.conf import settings

from baseapp_cloudflare_stream_field.stream import StreamClient

stream_client = StreamClient()


@shared_task
def refresh_from_cloudflare(content_type_pk, object_pk, attname, retries=1):
    from django.contrib.contenttypes.models import ContentType

    content_type = ContentType.objects.get(pk=content_type_pk)
    obj = content_type.get_object_for_this_type(pk=object_pk)
    cloudflare_video = getattr(obj, attname)

    if cloudflare_video["status"]["state"] != "ready":
        new_value = stream_client.get_video_data(cloudflare_video["uid"])
        setattr(obj, attname, new_value)

        if new_value["status"]["errorReasonCode"] == "ERR_DURATION_EXCEED_CONSTRAINT":
            obj.delete()
        elif (
            new_value["status"]["state"] == "ready"
            and new_value["status"]["errorReasonCode"] != "ERR_DURATION_EXCEED_CONSTRAINT"
        ):
            if (
                getattr(settings, "CLOUDFLARE_VIDEO_AUTOMATIC_TRIM", False)
                and hasattr(settings, "CLOUDFLARE_VIDEO_TRIM_DURATION_SECONDS")
                and new_value["clippedFrom"] is None
            ):
                old_video_uid = new_value["uid"]
                new_video = stream_client.clip_video(
                    {
                        "clippedFromVideoUID": old_video_uid,
                        "startTimeSeconds": 0,
                        "endTimeSeconds": settings.CLOUDFLARE_VIDEO_TRIM_DURATION_SECONDS,
                    }
                )
                if new_video:
                    setattr(obj, attname, new_video)
                    delete_original_trimmed_video.apply_async(
                        kwargs={
                            "old_video_uid": old_video_uid,
                            "new_video_uid": new_video["uid"],
                        },
                    )

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
def generate_download_url(content_type_pk, object_pk, attname, retries=1):
    from django.contrib.contenttypes.models import ContentType

    content_type = ContentType.objects.get(pk=content_type_pk)
    obj = content_type.get_object_for_this_type(pk=object_pk)
    cloudflare_video = getattr(obj, attname)

    if cloudflare_video["status"]["state"] != "ready" and retries < 1000:
        generate_download_url.apply_async(
            kwargs={
                "content_type_pk": content_type_pk,
                "object_pk": object_pk,
                "attname": attname,
                "retries": retries + 1,
            },
            countdown=20 * retries,
        )
        return None

    if (
        cloudflare_video["status"]["state"] == "ready"
        and "download_url" not in cloudflare_video["meta"]
    ):
        response = stream_client.download_video(cloudflare_video["uid"])
        download_url = response["result"]["default"]["url"]
        cloudflare_video["meta"]["download_url"] = download_url
        stream_client.update_video_data(cloudflare_video["uid"], {"meta": cloudflare_video["meta"]})
        setattr(obj, attname, cloudflare_video)
        obj.save(update_fields=[attname])


@shared_task
def clip_video(content_type_pk, object_pk, attname, retries=1):
    from django.contrib.contenttypes.models import ContentType

    content_type = ContentType.objects.get(pk=content_type_pk)
    obj = content_type.get_object_for_this_type(pk=object_pk)
    cloudflare_video = getattr(obj, attname)

    if cloudflare_video["status"]["state"] == "ready":
        stream_client.clip_video(
            {
                "clippedFromVideoUID": cloudflare_video["uid"],
                "startTimeSeconds": 0,
                "endTimeSeconds": settings.CLOUDFLARE_VIDEO_TRIM_DURATION_SECONDS,
            }
        )
    elif retries < 1000:
        clip_video.apply_async(
            kwargs={
                "content_type_pk": content_type_pk,
                "object_pk": object_pk,
                "attname": attname,
                "retries": retries + 1,
            },
            countdown=20 * retries,
        )


@shared_task
def delete_original_trimmed_video(old_video_uid, new_video_uid, retries=1):
    new_video = stream_client.get_video_data(new_video_uid)

    if new_video["status"]["state"] == "ready":
        stream_client.delete_video_data(old_video_uid)
    elif retries < 1000:
        delete_original_trimmed_video.apply_async(
            kwargs={
                "old_video_uid": old_video_uid,
                "new_video_uid": new_video_uid,
                "retries": retries + 1,
            },
            countdown=20 * retries,
        )
