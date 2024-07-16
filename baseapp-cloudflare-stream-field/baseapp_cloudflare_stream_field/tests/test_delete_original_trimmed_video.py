from unittest.mock import patch

import pytest

from baseapp_cloudflare_stream_field.tasks import delete_original_trimmed_video

pytestmark = pytest.mark.django_db


@patch("baseapp_cloudflare_stream_field.tasks.stream_client.get_video_data")
@patch("baseapp_cloudflare_stream_field.tasks.stream_client.delete_video_data")
def test_delete_original_trimmed_video_ready(mock_delete_video_data, mock_get_video_data):
    mock_get_video_data.return_value = {
        "status": {"state": "ready"},
        "meta": {},
        "uid": "new_video_uid",
    }

    delete_original_trimmed_video("old_video_uid", "new_video_uid")

    mock_delete_video_data.assert_called_once_with("old_video_uid")


@patch("baseapp_cloudflare_stream_field.tasks.stream_client.get_video_data")
def test_delete_original_trimmed_video_retry(mock_get_video_data):
    mock_get_video_data.return_value = {
        "status": {"state": "pending"},
        "meta": {},
        "uid": "new_video_uid",
    }

    with patch(
        "baseapp_cloudflare_stream_field.tasks.delete_original_trimmed_video.apply_async"
    ) as mock_apply_async:
        delete_original_trimmed_video("old_video_uid", "new_video_uid", retries=1)

        mock_apply_async.assert_called_once_with(
            kwargs={
                "old_video_uid": "old_video_uid",
                "new_video_uid": "new_video_uid",
                "retries": 2,
            },
            countdown=20,
        )
