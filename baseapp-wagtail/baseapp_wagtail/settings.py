from baseapp_core.tests.settings import *  # noqa

if 'INSTALLED_APPS' not in globals():
    INSTALLED_APPS = []
if 'MIDDLEWARE' not in globals():
    MIDDLEWARE = []

INSTALLED_APPS += [
    # wagtail
    "wagtail.contrib.settings",
    "wagtail.contrib.redirects",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail.locales",
    "wagtail.api.v2",  # TODO: Add setting to activate.
    'wagtail',
    # wagtail dependencies
    "modelcluster",
    "taggit",
    # wagtail-headless-preview
    "wagtail_headless_preview",  # TODO: Add setting to activate.
    # wagtail-styleguide (for development only)
    "wagtail.contrib.styleguide",  # TODO: Add setting to activate only in development.
]

MIDDLEWARE += [
    'wagtail.contrib.redirects.middleware.RedirectMiddleware',
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
WAGTAIL_SITE_NAME = "TMP NAME"  # TODO: Add setting to define.
WAGTAILADMIN_BASE_URL = "http://localhost:8000/"  # TODO: Dinamize the right way.

# TODO: Add setting to activate.
# Wagtail Preview
FRONT_HEADLESS_URL = "http://localhost:3000"  # TODO: load from settings
WAGTAIL_HEADLESS_PREVIEW = {
    "CLIENT_URLS": {"default": f'{FRONT_HEADLESS_URL}/page-preview'},
    "ENFORCE_TRAILING_SLASH": False,
}

WAGTAILDOCS_EXTENSIONS = ['csv', 'docx', 'key', 'odt', 'pdf', 'pptx', 'rtf', 'txt', 'xlsx', 'zip']
