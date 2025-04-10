import pytest

from baseapp_cloudflare_stream_field.stream import StreamClient

pytestmark = pytest.mark.django_db


def test_get_video_data(stream_client: StreamClient, video_uid, mock_get_video_data):
    r = stream_client.get_video_data(video_uid)
    assert r["uid"] == video_uid


def test_upload_via_link(stream_client: StreamClient, video_uid, mock_upload_via_link):
    r = stream_client.upload_via_link("https://example.com/video.mp4", meta={"title": "Test Video"})
    assert r["uid"] == video_uid


def test_update_video_data(stream_client: StreamClient, video_uid, mock_update_video_data):
    r = stream_client.update_video_data(video_uid=video_uid, data={"title": "Test Video"})
    assert r["uid"] == video_uid


def test_upload_caption_file(stream_client: StreamClient, video_uid, mock_upload_caption_file):
    r = stream_client.upload_caption_file(video_uid, "en", caption_file="test.srt")
    assert r["success"] is True
    assert r["result"]["uid"] == video_uid


def test_delete_video_data(stream_client: StreamClient, video_uid, mock_delete_video_data):
    r = stream_client.delete_video_data(video_uid)
    assert r.status_code == 200


def test_list_videos(stream_client: StreamClient, video_uid, mock_list_videos):
    r = stream_client.list_videos()
    assert r["result"][0]["uid"] == video_uid


def test_download_video(stream_client: StreamClient, video_uid, mock_download_video):
    r = stream_client.download_video(video_uid)
    assert r["success"] is True


def test_clip_video(stream_client: StreamClient, video_uid, mock_clip_video):
    data = {
        "allowedOrigins": ["example.com"],
        "clippedFromVideoUID": video_uid,
        "creator": "creator-id_abcde12345",
        "endTimeSeconds": 0,
        "maxDurationSeconds": 1,
        "requireSignedURLs": True,
        "startTimeSeconds": 0,
        "thumbnailTimestampPct": 0.529241,
        "watermark": {"uid": "ea95132c15732412d22c1476fa83f27a"},
    }
    r = stream_client.clip_video(data)
    assert r["clippedFromVideoUID"] == video_uid
