# BaseApp Social Auth - Django

## Usage

Use this package to login/signup using social networks (Facebook, Google and others)

[Full documentation](https://github.com/st4lk/django-rest-social-auth#oauth-10a-workflow-with-rest-social-auth)

## Installation

### Install the package

Install in your environment:

```bash
pip install baseapp-social-auth
```

### Add to your routes

```python
from baseapp_social_auth.views import SocialAuthViewSet  # noqa
router.register(r"social-auth", SocialAuthViewSet, basename="social-auth")
```

### Add INSTALLED_APPS

```python
INSTALLED_APPS = [
    ...
    "social_django",
    "rest_social_auth",
    "baseapp_social_auth.cache",
    ...
]
```

### Add CELERY_BEAT_SCHEDULE

```
"clean-up-social-auth-cache": {
    "task": "baseapp_social_auth.cache.tasks.clean_up_social_auth_cache",
    "schedule": timedelta(hours=1),
    "options": {"expires": 60 * 30},
},
```

### Add your settings

```python
from baseapp_social_auth.settings import (  # noqa
    SOCIAL_AUTH_BEAT_SCHEDULES,
    SOCIAL_AUTH_FACEBOOK_KEY,
    SOCIAL_AUTH_FACEBOOK_PROFILE_EXTRA_PARAMS,
    SOCIAL_AUTH_FACEBOOK_SCOPE,
    SOCIAL_AUTH_FACEBOOK_SECRET,
    SOCIAL_AUTH_LINKEDIN_OAUTH2_FIELD_SELECTORS,
    SOCIAL_AUTH_LINKEDIN_OAUTH2_KEY,
    SOCIAL_AUTH_LINKEDIN_OAUTH2_SCOPE,
    SOCIAL_AUTH_LINKEDIN_OAUTH2_SECRET,
    SOCIAL_AUTH_GOOGLE_OAUTH2_KEY,
    SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET,
    SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE,
    SOCIAL_AUTH_GOOGLE_OAUTH2_AUTH_EXTRA_ARGUMENTS,
    SOCIAL_AUTH_TWITTER_KEY,
    SOCIAL_AUTH_TWITTER_SECRET,
    SOCIAL_AUTH_PIPELINE,
    SOCIAL_AUTH_USER_FIELDS,
)
if SOCIAL_AUTH_FACEBOOK_KEY and SOCIAL_AUTH_FACEBOOK_SECRET:
    AUTHENTICATION_BACKENDS.append("social_core.backends.facebook.FacebookOAuth2")
if SOCIAL_AUTH_TWITTER_KEY and SOCIAL_AUTH_TWITTER_SECRET:
    AUTHENTICATION_BACKENDS.append("social_core.backends.twitter.TwitterOAuth")
if SOCIAL_AUTH_LINKEDIN_OAUTH2_KEY and SOCIAL_AUTH_LINKEDIN_OAUTH2_SECRET:
    AUTHENTICATION_BACKENDS.append("social_core.backends.linkedin.LinkedinOAuth2")\
if SOCIAL_AUTH_GOOGLE_OAUTH2_KEY and SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET:
    AUTHENTICATION_BACKENDS.append("social_core.backends.google.GoogleOAuth2")\
SOCIAL_AUTH_PIPELINE_MODULE = "apps.users.pipeline"
```

### Export variables in ansible

```
SOCIAL_AUTH_FACEBOOK_KEY
SOCIAL_AUTH_FACEBOOK_SECRET
SOCIAL_AUTH_TWITTER_KEY
SOCIAL_AUTH_TWITTER_SECRET
SOCIAL_AUTH_LINKEDIN_KEY
SOCIAL_AUTH_LINKEDIN_SECRET
SOCIAL_AUTH_GOOGLE_KEY
SOCIAL_AUTH_GOOGLE_SECRET
```

## Testing

Install the requirements from `test/requirements.txt` and run `pytest`
