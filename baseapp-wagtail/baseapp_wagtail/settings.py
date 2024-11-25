from urllib.parse import urljoin

from baseapp_core.settings.env import env

WAGTAIL_INSTALLED_APPS = [
    # wagtail-headless-preview
    "wagtail_headless_preview",
    # wagtail
    "wagtail.api.v2",
    "wagtail.contrib.settings",
    "wagtail.contrib.redirects",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail.locales",
    "wagtail.users",
    "wagtail",
    # wagtail dependencies
    "modelcluster",
    "taggit",
]

WAGTAIL_INSTALLED_INTERNAL_APPS = [
    "baseapp_wagtail",
    "baseapp_wagtail.base",
    "baseapp_wagtail.medias",
]

WAGTAIL_MIDDLEWARE = [
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]

# Locale settings
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_L10N = True
USE_TZ = True

WAGTAIL_CONTENT_LANGUAGES = LANGUAGES = [
    ("en", "English"),
]

# Wagtail settings
WAGTAILADMIN_BASE_URL = env("URL", default="http://localhost:8000")

# Wagtail Preview
if "FRONT_URL" not in globals():
    FRONT_URL = env("FRONT_URL", "", required=False)

FRONT_HEADLESS_URL = urljoin(FRONT_URL, env("WAGTAIL_FRONT_URL_PATH", default="/pages"))
FRONT_PAGE_PREVIEW_URL = urljoin(
    FRONT_URL, env("WAGTAIL_FRONT_PAGE_PREVIEW_URL_PATH", default="/page-preview")
)
WAGTAIL_HEADLESS_PREVIEW = {
    "CLIENT_URLS": {"default": f"{FRONT_PAGE_PREVIEW_URL}"},
    "ENFORCE_TRAILING_SLASH": False,
}

WAGTAILIMAGES_IMAGE_MODEL = "baseapp_wagtail_medias.CustomImage"
WAGTAILDOCS_DOCUMENT_MODEL = "baseapp_wagtail_medias.CustomDocument"
WAGTAILDOCS_EXTENSIONS = ["csv", "docx", "key", "odt", "pdf", "pptx", "rtf", "txt", "xlsx", "zip"]

"""
These are the settings that must be defined in the project settings:
- WAGTAIL_SITE_NAME

And these are the settings that you must add to the .env file:
- WAGTAILADMIN_BASE_URL | env: URL
    -- URL of the Wagtail admin. This shouldn't have the path, unless there is a specific rule in
    the Nginx, for example.
    -- This is a recycled env var from the baseapp-core.
- FRONT_HEADLESS_URL | env: FRONT_URL + WAGTAIL_FRONT_URL_PATH
    -- URL PATH of the front-end application that will consume the API. The path of the URL must
    point to where the pages will be rendered.
    -- This is a new env var designed only for Wagtail.
- FRONT_PAGE_PREVIEW_URL | env: FRONT_URL + WAGTAIL_FRONT_PAGE_PREVIEW_URL_PATH
    -- URL PATH of the front-end application that will render the page previews.
    -- This is a new env var designed only for Wagtail.
"""
