# BaseApp E2E

Utilities for database initialization and seeding from a frontend End-To-End test client (typically Cypress): a DRF `E2EViewSet` to load/flush data and set passwords during tests.

`baseapp_e2e` follows the [plugin architecture](../baseapp_core/plugins/README.md): it registers itself as a plugin and contributes the `E2E` settings scaffold (defaulting to `{"ENABLED": False}`) via the registry. The DRF viewset is wired manually (see [installation](#installation)), and every endpoint is guarded by the `E2eEnabled` permission, so the API is inert unless you explicitly set `E2E["ENABLED"] = True` — keep it disabled in production.

## Usage

This project includes utilities for database initialization and seeding when performing End-To-End tests.

### E2E Endpoints

[E2EViewSet](baseapp_e2e/rest_framework/views.py) has a set of endpoints for managing the test data from the frontend E2E test client (usually from Cypress):

* POST `/load-data` - load data using [Django's default serizlization format](https://docs.djangoproject.com/en/4.2/topics/serialization/#serialization-formats-json). Example payload:

``` json
{
    "objects": [{
        "model": "users.user",
        "fields": {
            "email": "abc@tsl.io",
            // ...
        }}, {
        "model": "users.user",
        "fields": {
            "email": "def@tsl.io",
            // ...
        }
    }]
}
```

* POST `/load-script` - load data through a script module that exists in the backend project repository. Example:

Set the `SCRIPTS_PACKAGE` setting to a module path where the scripts are located:

```py
E2E = {
    "ENABLED": True,
    "SCRIPTS_PACKAGE": "e2e.scripts",
}
```

Then add a python script on the defined module path, e.g.: `<project-root>/e2e/scripts/users.py`. The script is expected to have a `def load()` function that will be executed by the endpoint.

```py
import tests.factories as f

def load():
    f.UserFactory()
```

To request the script to be run use request format as:

``` json
{
    "scripts": ["users"]
}
```

* POST `/flush-data` - remove the data from database using [Django flush command](https://docs.djangoproject.com/en/4.2/ref/django-admin/#flush)
* POST `/set-password` - set a password for an existing user. Example payload:

``` json
{
    "user": <user id>,
    "password": "1234"
}
```

## Demo

There is a [test project](testproject/) with a complete demo set up.

## Installation

Install in your environment:

```bash
pip install baseapp-backend
```

### Settings

Add the app to your project INSTALLED_APPS:

```py
INSTALLED_APPS = [
    ...
    "baseapp_e2e",
]
```

Enable E2E and point it at your scripts module (the plugin ships this setting defaulting to `{"ENABLED": False}`, so you override it to switch the endpoints on):

```py
E2E = {
    "ENABLED": True,
    "SCRIPTS_PACKAGE": "e2e.scripts",
}
```

Register the viewset on a DRF router (the package does not contribute URLs itself), e.g. in your `urls.py`:

```py
from baseapp_e2e.rest_framework.views import E2EViewSet

router.register(r"e2e", E2EViewSet, basename="e2e")
```

The endpoints above are then served under that prefix (e.g. `e2e/load-data`, `e2e/flush-data`, `e2e/load-script`, `e2e/set-password`).

## How to develop

General development instructions can be found in the [main README](../README.md#how-to-develop).
