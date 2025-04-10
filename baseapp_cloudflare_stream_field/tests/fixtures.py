import json
from unittest.mock import patch

import httpretty
import pytest
from django.conf import settings
from django.contrib.contenttypes.models import ContentType

from baseapp_cloudflare_stream_field.stream import StreamClient
from testproject.testapp.models import Post


@pytest.fixture
def use_httpretty():
    httpretty.enable()
    httpretty.HTTPretty.allow_net_connect = False
    yield
    httpretty.disable()
    httpretty.reset()


@pytest.fixture
def stream_client():
    return StreamClient()


@pytest.fixture
def account_id():
    return settings.CLOUDFLARE_ACCOUNT_ID


@pytest.fixture
def video_uid():
    return "6b9e68b07dfee8cc2d116e4c51d6a957"


@pytest.fixture
def clipped_video_uid():
    return "64b280da11154c63862de71560b9a684"


@pytest.fixture
def setup_video_not_ready(video_uid):
    with patch("baseapp_cloudflare_stream_field.tasks.refresh_from_cloudflare.apply_async"):
        content_type = ContentType.objects.get_for_model(Post)
        obj = Post.objects.create()
        obj.video = {"status": {"state": "pending"}, "meta": {}, "uid": video_uid}
        obj.save()
    return content_type, obj


@pytest.fixture
def setup_video_ready_no_url(video_uid):
    with patch("baseapp_cloudflare_stream_field.tasks.refresh_from_cloudflare.apply_async"):
        content_type = ContentType.objects.get_for_model(Post)
        obj = Post.objects.create()
        obj.video = {"status": {"state": "ready"}, "meta": {}, "uid": video_uid}
        obj.save()
    return content_type, obj


@pytest.fixture
def setup_video_ready_with_url(video_uid):
    with patch("baseapp_cloudflare_stream_field.tasks.refresh_from_cloudflare.apply_async"):
        content_type = ContentType.objects.get_for_model(Post)
        obj = Post.objects.create()
        obj.video = {
            "status": {"state": "ready", "errorReasonCode": None, "clippedFrom": None},
            "meta": {"download_url": "http://existing.download.url"},
            "uid": video_uid,
        }
        obj.save()
    return content_type, obj


@pytest.fixture
def setup_video_ready_with_error(video_uid):
    content_type = ContentType.objects.get_for_model(Post)
    obj = Post.objects.create()
    obj.video = {
        "status": {"state": "ready", "errorReasonCode": "ERR_DURATION_EXCEED_CONSTRAINT"},
        "meta": {},
        "uid": video_uid,
    }
    obj.save()
    return content_type, obj


@pytest.fixture
def mock_get_video_data(use_httpretty, account_id, video_uid):
    httpretty.register_uri(
        httpretty.GET,
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/stream/{video_uid}",
        body=json.dumps(
            {
                "result": {
                    "uid": video_uid,
                    "preview": f"https://customer-f33zs165nr7gyfy4.cloudflarestream.com/{video_uid}/watch",
                    "thumbnail": f"https://customer-f33zs165nr7gyfy4.cloudflarestream.com/{video_uid}/thumbnails/thumbnail.jpg",
                    "readyToStream": True,
                    "status": {"state": "ready"},
                    "meta": {
                        "downloaded-from": "https://storage.googleapis.com/stream-example-bucket/video.mp4",
                        "name": "My First Stream Video",
                    },
                    "created": "2020-10-16T20:20:17.872170843Z",
                    "clippedFrom": None,
                    "size": 9032701,
                },
                "success": True,
                "errors": [],
                "messages": [],
            }
        ),
    )


@pytest.fixture
def mock_upload_via_link(use_httpretty, account_id, video_uid):
    httpretty.register_uri(
        httpretty.POST,
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/stream/copy",
        body=json.dumps(
            {
                "result": {
                    "uid": video_uid,
                    "preview": f"https://customer-f33zs165nr7gyfy4.cloudflarestream.com/{video_uid}/watch",
                    "thumbnail": f"https://customer-f33zs165nr7gyfy4.cloudflarestream.com/{video_uid}/thumbnails/thumbnail.jpg",
                    "readyToStream": True,
                    "status": {"state": "ready"},
                    "meta": {
                        "downloaded-from": "https://storage.googleapis.com/stream-example-bucket/video.mp4",
                        "name": "My First Stream Video",
                    },
                    "created": "2020-10-16T20:20:17.872170843Z",
                    "size": 9032701,
                },
                "success": True,
                "errors": [],
                "messages": [],
            }
        ),
    )


@pytest.fixture
def mock_update_video_data(use_httpretty, account_id, video_uid):
    httpretty.register_uri(
        httpretty.POST,
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/stream/{video_uid}",
        body=json.dumps(
            {
                "result": {
                    "uid": video_uid,
                    "preview": f"https://customer-f33zs165nr7gyfy4.cloudflarestream.com/{video_uid}/watch",
                    "thumbnail": f"https://customer-f33zs165nr7gyfy4.cloudflarestream.com/{video_uid}/thumbnails/thumbnail.jpg",
                    "readyToStream": True,
                    "status": {"state": "ready"},
                    "meta": {
                        "downloaded-from": "https://storage.googleapis.com/stream-example-bucket/video.mp4",
                        "name": "My First Stream Video",
                    },
                    "created": "2020-10-16T20:20:17.872170843Z",
                    "size": 9032701,
                },
                "success": True,
                "errors": [],
                "messages": [],
            }
        ),
    )


@pytest.fixture
def mock_upload_caption_file(use_httpretty, account_id, video_uid):
    httpretty.register_uri(
        httpretty.PUT,
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/stream/{video_uid}/captions/en",
        body=json.dumps(
            {
                "result": {
                    "uid": video_uid,
                    "preview": f"https://customer-f33zs165nr7gyfy4.cloudflarestream.com/{video_uid}/watch",
                    "thumbnail": f"https://customer-f33zs165nr7gyfy4.cloudflarestream.com/{video_uid}/thumbnails/thumbnail.jpg",
                    "readyToStream": True,
                    "status": {"state": "ready"},
                    "meta": {
                        "downloaded-from": "https://storage.googleapis.com/stream-example-bucket/video.mp4",
                        "name": "My First Stream Video",
                    },
                    "created": "2020-10-16T20:20:17.872170843Z",
                    "size": 9032701,
                },
                "success": True,
                "errors": [],
                "messages": [],
            }
        ),
    )


@pytest.fixture
def mock_delete_video_data(use_httpretty, account_id, video_uid):
    httpretty.register_uri(
        httpretty.DELETE,
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/stream/{video_uid}",
    )


@pytest.fixture
def mock_list_videos(use_httpretty, account_id, video_uid):
    httpretty.register_uri(
        httpretty.GET,
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/stream",
        body=json.dumps(
            {
                "errors": [],
                "messages": [],
                "success": True,
                "result": [
                    {
                        "allowedOrigins": ["example.com"],
                        "created": "2014-01-02T02:20:00Z",
                        "creator": "creator-id_abcde12345",
                        "duration": 0,
                        "input": {"height": 0, "width": 0},
                        "liveInput": "fc0a8dc887b16759bfd9ad922230a014",
                        "maxDurationSeconds": 1,
                        "meta": {"name": "video12345.mp4"},
                        "modified": "2014-01-02T02:20:00Z",
                        "playback": {
                            "dash": "https://customer-m033z5x00ks6nunl.cloudflarestream.com/ea95132c15732412d22c1476fa83f27a/manifest/video.mpd",
                            "hls": "https://customer-m033z5x00ks6nunl.cloudflarestream.com/ea95132c15732412d22c1476fa83f27a/manifest/video.m3u8",
                        },
                        "preview": "https://customer-m033z5x00ks6nunl.cloudflarestream.com/ea95132c15732412d22c1476fa83f27a/watch",
                        "readyToStream": True,
                        "readyToStreamAt": "2014-01-02T02:20:00Z",
                        "requireSignedURLs": True,
                        "scheduledDeletion": "2014-01-02T02:20:00Z",
                        "size": 4190963,
                        "status": {
                            "errorReasonCode": "ERR_NON_VIDEO",
                            "errorReasonText": "The file was not recognized as a valid video file.",
                            "pctComplete": "string",
                            "state": "inprogress",
                        },
                        "thumbnail": "https://customer-m033z5x00ks6nunl.cloudflarestream.com/ea95132c15732412d22c1476fa83f27a/thumbnails/thumbnail.jpg",
                        "thumbnailTimestampPct": 0.529241,
                        "uid": video_uid,
                        "uploadExpiry": "2014-01-02T02:20:00Z",
                        "uploaded": "2014-01-02T02:20:00Z",
                        "watermark": {
                            "created": "2014-01-02T02:20:00Z",
                            "downloadedFrom": "https://company.com/logo.png",
                            "height": 0,
                            "name": "Marketing Videos",
                            "opacity": 0.75,
                            "padding": 0.1,
                            "position": "center",
                            "scale": 0.1,
                            "size": 29472,
                            "uid": "ea95132c15732412d22c1476fa83f27a",
                            "width": 0,
                        },
                    }
                ],
                "range": 1000,
                "total": 35586,
            }
        ),
    )


@pytest.fixture
def mock_download_video(use_httpretty, account_id, video_uid):
    httpretty.register_uri(
        httpretty.POST,
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/stream/{video_uid}/downloads",
        body=json.dumps({"errors": [], "messages": [], "success": True, "result": {}}),
    )


@pytest.fixture
def mock_clip_video(use_httpretty, account_id, clipped_video_uid, video_uid):
    httpretty.register_uri(
        httpretty.POST,
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/stream/clip",
        body=json.dumps(
            {
                "errors": [],
                "messages": [],
                "success": True,
                "result": {
                    "uid": clipped_video_uid,
                    "allowedOrigins": ["example.com"],
                    "clippedFromVideoUID": video_uid,
                    "created": "2014-01-02T02:20:00Z",
                    "creator": "creator-id_abcde12345",
                    "endTimeSeconds": 0,
                    "maxDurationSeconds": 1,
                    "meta": {"name": "video12345.mp4"},
                    "modified": "2014-01-02T02:20:00Z",
                    "playback": {
                        "dash": "https://customer-m033z5x00ks6nunl.cloudflarestream.com/ea95132c15732412d22c1476fa83f27a/manifest/video.mpd",
                        "hls": "https://customer-m033z5x00ks6nunl.cloudflarestream.com/ea95132c15732412d22c1476fa83f27a/manifest/video.m3u8",
                    },
                    "preview": "https://customer-m033z5x00ks6nunl.cloudflarestream.com/ea95132c15732412d22c1476fa83f27a/watch",
                    "requireSignedURLs": True,
                    "startTimeSeconds": 0,
                    "status": "inprogress",
                    "thumbnailTimestampPct": 0.529241,
                    "watermark": {"uid": "ea95132c15732412d22c1476fa83f27a"},
                },
            }
        ),
    )
