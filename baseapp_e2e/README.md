# BaseApp E2E

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

Add E2E settings to Django settings file of your application:

```py
E2E = {
    "ENABLED": True,
    "SCRIPTS_PACKAGE": "e2e.scripts",
}
```

## How to delevop

General development instructions can be found in [main README](..#testing)
