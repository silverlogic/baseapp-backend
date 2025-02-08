from unittest.mock import patch

import pytest
from django.conf import settings

from baseapp_cloudflare_stream_field.tasks import refresh_from_cloudflare
from testproject.testapp.models import Post


@pytest.mark.django_db
@patch("baseapp_cloudflare_stream_field.tasks.stream_client.get_video_data")
@patch("baseapp_cloudflare_stream_field.tasks.stream_client.clip_video")
@patch("baseapp_cloudflare_stream_field.tasks.delete_original_trimmed_video.apply_async")
@patch("django.contrib.contenttypes.models.ContentType.objects.get")
def test_refresh_from_cloudflare_ready_no_trim(
    mock_get_content_type,
    mock_delete_async,
    mock_clip_video,
    mock_get_video_data,
    setup_video_not_ready,
    video_uid,
):
    content_type, obj = setup_video_not_ready

    mock_get_content_type.return_value = content_type
    mock_get_video_data.return_value = {
        "status": {"state": "ready", "errorReasonCode": None, "clippedFrom": None},
        "meta": {},
        "uid": video_uid,
    }

    with patch.object(settings, "CLOUDFLARE_VIDEO_AUTOMATIC_TRIM", False):
        refresh_from_cloudflare(content_type.pk, obj.pk, "video")

        obj.refresh_from_db()
        assert obj.video["uid"] == video_uid
        mock_get_video_data.assert_called_once_with(video_uid)
        mock_clip_video.assert_not_called()
        mock_delete_async.assert_not_called()


@pytest.mark.django_db
@patch("baseapp_cloudflare_stream_field.tasks.stream_client.get_video_data")
@patch("baseapp_cloudflare_stream_field.tasks.refresh_from_cloudflare.apply_async")
@patch("django.contrib.contenttypes.models.ContentType.objects.get")
def test_refresh_from_cloudflare_not_ready(
    mock_get_content_type, mock_apply_async, mock_get_video_data, setup_video_not_ready, video_uid
):
    content_type, obj = setup_video_not_ready

    mock_get_content_type.return_value = content_type
    mock_get_video_data.return_value = {
        "status": {"state": "not_ready", "errorReasonCode": None},
        "meta": {},
        "uid": video_uid,
    }

    refresh_from_cloudflare(content_type.pk, obj.pk, "video", retries=1)

    obj.refresh_from_db()
    assert obj.video["uid"] == video_uid
    mock_get_video_data.assert_called_once_with(video_uid)
    mock_apply_async.assert_called_once_with(
        kwargs={
            "content_type_pk": content_type.pk,
            "object_pk": obj.pk,
            "attname": "video",
            "retries": 2,
        },
        countdown=20 * 1,
    )


@pytest.mark.django_db
@patch("baseapp_cloudflare_stream_field.tasks.stream_client.get_video_data")
@patch("django.contrib.contenttypes.models.ContentType.objects.get")
def test_refresh_from_cloudflare_ready_with_error(
    mock_get_content_type, mock_get_video_data, setup_video_not_ready, video_uid
):
    content_type, obj = setup_video_not_ready

    mock_get_content_type.return_value = content_type
    mock_get_video_data.return_value = {
        "status": {"state": "ready", "errorReasonCode": "ERR_DURATION_EXCEED_CONSTRAINT"},
        "meta": {},
        "uid": video_uid,
    }

    refresh_from_cloudflare(content_type.pk, obj.pk, "video")

    with pytest.raises(Post.DoesNotExist):
        obj.refresh_from_db()

    mock_get_video_data.assert_called_once_with(video_uid)


@pytest.mark.django_db
@patch("baseapp_cloudflare_stream_field.tasks.stream_client.get_video_data")
@patch("baseapp_cloudflare_stream_field.tasks.stream_client.clip_video")
@patch("baseapp_cloudflare_stream_field.tasks.delete_original_trimmed_video.apply_async")
@patch("django.contrib.contenttypes.models.ContentType.objects.get")
def test_refresh_from_cloudflare_ready_with_trim(
    mock_get_content_type,
    mock_delete_async,
    mock_clip_video,
    mock_get_video_data,
    setup_video_not_ready,
    video_uid,
):
    content_type, obj = setup_video_not_ready

    mock_get_content_type.return_value = content_type
    mock_get_video_data.return_value = {
        "status": {"state": "ready", "errorReasonCode": None, "clippedFrom": None},
        "meta": {},
        "uid": video_uid,
        "clippedFrom": None,
    }

    new_video_uid = "67890"
    mock_clip_video.return_value = {
        "uid": new_video_uid,
        "clippedFrom": video_uid,
        "status": {"state": "ready"},
    }

    with patch.object(settings, "CLOUDFLARE_VIDEO_AUTOMATIC_TRIM", True), patch.object(
        settings, "CLOUDFLARE_VIDEO_TRIM_DURATION_SECONDS", 60
    ):
        refresh_from_cloudflare(content_type.pk, obj.pk, "video")

        obj.refresh_from_db()
        assert obj.video["uid"] == new_video_uid
        mock_get_video_data.assert_called_once_with(video_uid)
        mock_clip_video.assert_called_once_with(
            {
                "clippedFromVideoUID": video_uid,
                "startTimeSeconds": 0,
                "endTimeSeconds": 60,
            }
        )
        mock_delete_async.assert_called_once_with(
            kwargs={"old_video_uid": video_uid, "new_video_uid": new_video_uid},
        )


@pytest.mark.django_db
@patch("baseapp_cloudflare_stream_field.tasks.stream_client.get_video_data")
@patch("django.contrib.contenttypes.models.ContentType.objects.get")
@patch("baseapp_cloudflare_stream_field.tasks.refresh_from_cloudflare.apply_async")
def test_refresh_from_cloudflare_retry_logic(
    mock_apply_async, mock_get_content_type, mock_get_video_data, setup_video_not_ready, video_uid
):
    content_type, obj = setup_video_not_ready

    mock_get_content_type.return_value = content_type
    mock_get_video_data.return_value = {
        "status": {"state": "not_ready", "errorReasonCode": None},
        "meta": {},
        "uid": video_uid,
    }

    refresh_from_cloudflare(content_type.pk, obj.pk, "video", retries=999)

    mock_apply_async.assert_called_once_with(
        kwargs={
            "content_type_pk": content_type.pk,
            "object_pk": obj.pk,
            "attname": "video",
            "retries": 1000,
        },
        countdown=20 * 999,
    )
    mock_get_video_data.assert_called_once_with(video_uid)
