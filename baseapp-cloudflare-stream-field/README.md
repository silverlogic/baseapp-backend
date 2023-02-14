# Django Cloudflare Stream Field

This app provides integration with Cloudflare Stream, where you can upload directly to Cloudflare using TUS protocol.

## Install the package

Add to `requirements/base.txt`:

```bash
django-cloudflare-stream @ git+https://github.com/silverlogic/django-cloudflare-stream.git
```

Add the following to your `settings/base.py`:

```python
# Cloudflare
CLOUDFLARE_ACCOUNT_ID = env("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_API_TOKEN = env("CLOUDFLARE_API_TOKEN")
CLOUDFLARE_AUTH_EMAIL = env("CLOUDFLARE_AUTH_EMAIL")
```

Include the URLs in your main `urls.py` file:

```python
re_path(r"^cloudflare-stream-upload/", include("cloudflare_stream_field.urls")),
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
from cloudflare_stream_field import CloudflareStreamField

class Post(models.Model):
    video = CloudflareStreamField(null=True, blank=True)
```



`CloudflareStreamField` inherits from `JSONField` so you can use any look it provides, like filter only for videos fully processed by Cloudflare:

```python
Post.objects.filter(video__status__state="ready")
```