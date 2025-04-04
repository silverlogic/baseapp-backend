# Django Cloudflare Stream Field

This app provides integration with Cloudflare Stream, where you can upload [directly to Cloudflare](https://developers.cloudflare.com/stream/uploading-videos/direct-creator-uploads/) using [TUS protocol](https://tus.io/).

## Install the package

Install in your environment:

```bash
pip install baseapp-cloudflare-stream-field
```

Add the following to your `settings/base.py`:

```python
# Cloudflare
CLOUDFLARE_ACCOUNT_ID = env("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_API_TOKEN = env("CLOUDFLARE_API_TOKEN")
CLOUDFLARE_AUTH_EMAIL = env("CLOUDFLARE_AUTH_EMAIL")

# Make sure to add the task routing for refresh_from_cloudflare and generate_download_url
CELERY_TASK_ROUTES = {
    "baseapp_cloudflare_stream_field.tasks.refresh_from_cloudflare": {
        "exchange": "default",
        "routing_key": "default",
    },
    "baseapp_cloudflare_stream_field.tasks.generate_download_url": {
        "exchange": "default",
        "routing_key": "default",
    },
}
```

This package offers the option to post-process the original video by trimming it to a predefined duration. This process creates a new trimmed video and then deletes the original one. To enable this behavior, you should add the following configurations:

```python
  CLOUDFLARE_VIDEO_TRIM_DURATION_SECONDS = Integer number
  CLOUDFLARE_VIDEO_MAX_DURATION_SECONDS = Integer number
  CLOUDFLARE_VIDEO_AUTOMATIC_TRIM = True/False
```

If you set ```CLOUDFLARE_VIDEO_AUTOMATIC_TRIM = True```, you must also specify a value for ```CLOUDFLARE_VIDEO_TRIM_DURATION_SECONDS```. This will trim the video to create a clip starting from the beginning and lasting up to your defined maximum duration. For example:

```python
  CLOUDFLARE_VIDEO_MAX_DURATION_SECONDS = 30
  CLOUDFLARE_VIDEO_AUTOMATIC_TRIM = True

  # Will create a new video from 0s to 30s
```

If ```CLOUDFLARE_VIDEO_MAX_DURATION_SECONDS``` is set, it will create a request to Cloudflare with the maxDurationSeconds parameter. This means that it will attempt to fail uploads where the video's duration exceeds the specified value. Setting this parameter is also a good option for restricting the amount of storage that pending uploads will use. By default, Cloudflare will use 14,400 seconds for URLs that have not been uploaded.

[Example](https://community.cloudflare.com/t/pending-videos-taking-up-a-large-amount-of-storage-quota/327634):

- A user begins uploading a video.
- The upload process is interrupted and cannot be completed due to an issue on the client's side.
- This interruption results in the creation of a 'pending video' instance under Cloudflare.
- If **maxDurationSeconds** is set to 30, then only 30 seconds' worth of video storage will be utilized from your account, as opposed to the default allocation of 14,400 seconds."

Include the URLs in your main `urls.py` file:

```python
re_path(r"^cloudflare-stream-upload/", include("baseapp_cloudflare_stream_field.urls")),
```

And if you use Django REST Framework, add the following to your router:

```python
# Cloudflare Stream Upload
from baseapp_cloudflare_stream_field.rest_framework import CloudflareStreamUploadViewSet

router.register(
    r"cloudflare-stream-upload", CloudflareStreamUploadViewSet, basename="cloudflare-stream-upload"
)
```

### Allow CORS Headers

You need to add `tus-resumable, upload-length, upload-metadata, upload-creator` to your CORS header. Add the following to `settings/base.py`:

```python
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "tus-resumable",
    "upload-length",
    "upload-metadata",
    "upload-creator"
]
```

## Usage

Import and use the field in your models file:

```python
from baseapp_cloudflare_stream_field import CloudflareStreamField

class Post(models.Model):
    video = CloudflareStreamField(null=True, blank=True, downloadable=False)
```

If you set `downloadable` to `True` it will automatically trigger a task to generate and save the download url at `obj.video['meta']['download_url']`.

`CloudflareStreamField` inherits from `JSONField` so you can use any look it provides, like filter only for videos fully processed by Cloudflare:

```python
Post.objects.filter(video__status__state="ready")
```


This package manages the video upload flow as follows:

- The client starts by creating a TUS (resumable upload protocol) request to your backend.
- Your server functions as a middleware, receiving this request and forwarding it to Cloudflare's endpoint.
- Upon receipt, Cloudflare provides a unique, one-time upload URL. TUS then manages the upload to this URL.
- Once the upload is complete, the client gets a response with the 'Stream-Media-ID' header, which contains a unique identifier for the video in Cloudflare.
- You then need to send this identifier (uid) back to your backend to create a new instance with the CloudflareStreamField. For example:

Example:

```python
Model.objects.create(video=uid)
````

This step ensures that your server's records are updated and in sync with the video's status on Cloudflare. 