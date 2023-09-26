# BaseApp E2E

## Usage

This project includes utilities for database initialization and seeding when performing End-To-End tests

### E2E Enpoints

[E2EViewSet](baseapp_e2e/rest_framework/views.py) has a set of endpoints for managing the test data from the frontend E2E test client (usually Cypress).

## Demo

There is a [test project](testproject/) with a complete demo set up.

## Installation

Add to requirements of yor project (replacing everything inside brackets):

```bash
baseapp-e2e @ git+https://github.com/silverlogic/baseapp-backend.git@v0.1#subdirectory=baseapp-e2e
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
    "SCRIPTS_PACKAGE": "baseapp_e2e.e2e_scripts",
}
```

## How to delevop

General development instructions can be found in [main README](..#testing)
