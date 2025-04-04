# BaseApp URL Shortening

Reusable app to enable url shortening.

## How to install:

Install in your environment:

```bash
pip install baseapp-url-shortening
```

And run provision or manually `pip install -r requirements/base.ext`

If you want to develop, [install using this other guide](#how-to-develop).

## How to use

Add `baseapp_url_shortening` to your project's `INSTALLED_APPS`

Add the following to your settings file. `URL_SHORTENING_PREFIX` can be any string

```py
URL_SHORTENING_PREFIX = "c"
```

Add the following to your apps/urls.py file

```py
urlpatterns = [
    re_path(r"", include("baseapp_url_shortening.urls")),
]
```

## Writing test cases in your project

There is a `ShortUrlFactory` which helps you write other factories:

```
import factory
from baseapp_url_shortening.tests.factories import ShortUrlFactory
```

## How to develop

Clone the project inside your project's backend dir:

```
git clone git@github.com:silverlogic/baseapp-backend.git
```

And manually install the package:

```
pip install -e baseapp-backend/baseapp-url-shortening
```

The `-e` flag will make it like any change you make in the cloned repo files will effect into the project.