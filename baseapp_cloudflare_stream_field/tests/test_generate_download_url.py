from unittest.mock import patch

import pytest

from baseapp_cloudflare_stream_field.tasks import generate_download_url

pytestmark = pytest.mark.django_db


def test_generate_download_url_not_ready(setup_video_not_ready):
    content_type, obj = setup_video_not_ready

    with patch(
        "baseapp_cloudflare_stream_field.tasks.generate_download_url.apply_async"
    ) as mock_apply_async:
        generate_download_url(content_type.pk, obj.pk, "video")

        mock_apply_async.assert_called_once_with(
            kwargs={
                "content_type_pk": content_type.pk,
                "object_pk": obj.pk,
                "attname": "video",
                "retries": 2,
            },
            countdown=20,
        )


@patch("baseapp_cloudflare_stream_field.tasks.stream_client.download_video")
@patch("baseapp_cloudflare_stream_field.tasks.stream_client.update_video_data")
def test_generate_download_url_ready_no_download_url(
    mock_update_video_data, mock_download_video, setup_video_ready_no_url
):
    content_type, obj = setup_video_ready_no_url

    mock_download_video.return_value = {"result": {"default": {"url": "http://new.download.url"}}}

    generate_download_url(content_type.pk, obj.pk, "video")

    obj.refresh_from_db()
    assert obj.video["meta"]["download_url"] == "http://new.download.url"
    mock_update_video_data.assert_called_once_with(obj.video["uid"], {"meta": obj.video["meta"]})


def test_generate_download_url_ready_with_download_url(setup_video_ready_with_url):
    content_type, obj = setup_video_ready_with_url

    with patch(
        "baseapp_cloudflare_stream_field.tasks.stream_client.download_video"
    ) as mock_download_video:
        generate_download_url(content_type.pk, obj.pk, "video")

        obj.refresh_from_db()
        assert obj.video["meta"]["download_url"] == "http://existing.download.url"
        mock_download_video.assert_not_called()
