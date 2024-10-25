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


<!-- # TODO: Add the following items  -->
1. Add to INSTALLED_APPS
2. Import settings.py
3. Load wagtail urls
4. Setup the page model
5. Add section to remove wagtail from the project and link this section to the template model

<!-- # TODO: DEV: -->
1. Explain tests setup_test script.

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
