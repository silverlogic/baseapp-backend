from baseapp_core.tests.settings import *  # noqa

INSTALLED_APPS += ["testproject.testapp"]


# Cloudflare
CLOUDFLARE_ACCOUNT_ID = "023e105f4ecef8ad9ca31a8372d0c353"
CLOUDFLARE_API_TOKEN = "1234567890abcdef1234567890abcdef"
CLOUDFLARE_AUTH_EMAIL = ""
CLOUDFLARE_VIDEO_AUTOMATIC_TRIM = True
CLOUDFLARE_VIDEO_TRIM_DURATION_SECONDS = 10

# Celery
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
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
