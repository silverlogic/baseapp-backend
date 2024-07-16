from unittest.mock import patch

import pytest
from django.conf import settings

from baseapp_cloudflare_stream_field.tasks import clip_video

pytestmark = pytest.mark.django_db


def test_clip_video_ready(setup_video_ready_with_url, video_uid):
    content_type, obj = setup_video_ready_with_url

    with patch.object(settings, "CLOUDFLARE_VIDEO_TRIM_DURATION_SECONDS", 60):
        with patch(
            "baseapp_cloudflare_stream_field.tasks.stream_client.clip_video"
        ) as mock_clip_video:
            clip_video(content_type.pk, obj.pk, "video")

            mock_clip_video.assert_called_once_with(
                {"clippedFromVideoUID": video_uid, "startTimeSeconds": 0, "endTimeSeconds": 60}
            )


def test_clip_video_retry(setup_video_not_ready):
    content_type, obj = setup_video_not_ready

    with patch("baseapp_cloudflare_stream_field.tasks.clip_video.apply_async") as mock_clip_video:
        clip_video(content_type.pk, obj.pk, "video", retries=1)

        mock_clip_video.assert_called_once_with(
            kwargs={
                "content_type_pk": content_type.pk,
                "object_pk": obj.pk,
                "attname": "video",
                "retries": 2,
            },
            countdown=20,
        )
