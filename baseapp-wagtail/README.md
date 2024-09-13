# BaseApp Wagtail - Django

## Usage

Use this package to load the Wagtail CMS initial Setup. You can also follow its internal code as a reference of how to implement features inside of the Wagtail CMS

[Wagtail documentation](https://docs.wagtail.org/en/stable/)

## Installation

### Install the package

Install in your environment:

```bash
pip install baseapp-wagtail
```

<!-- # TODO: Review the following section -->
### Add to your routes

```python
from baseapp_social_auth.views import SocialAuthViewSet  # noqa
router.register(r"social-auth", SocialAuthViewSet, basename="social-auth")
```

### Add INSTALLED_APPS

```python
INSTALLED_APPS = [
    ...
    "baseapp_wagtail",
    ...
]
```

<!-- # TODO: Review the following section -->
### Add CELERY_BEAT_SCHEDULE

```
"clean-up-social-auth-cache": {
    "task": "baseapp_social_auth.cache.tasks.clean_up_social_auth_cache",
    "schedule": timedelta(hours=1),
    "options": {"expires": 60 * 30},
},
```

<!-- # TODO: Document all customizable settings -->
### Add your settings

```python

```

## Testing

Install the requirements from `test/requirements.txt` and run `pytest`
