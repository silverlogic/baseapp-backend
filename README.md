# BaseApp Backend

This repository contains baseapp django packages to be reused accross projects based on TSL's BaseApp

## [baseapp-core](baseapp-core)

The core contains the basics for BaseApp like Django Rest Framework's basic setup, custom ModelSerializer and fields, also base email template, testing helpers and other utilities.

## [baseapp-auth](baseapp-auth)

Contains the following apps:

**baseapp_auth**: Reusable user and authentication utilities. Authentication setup using AuthToken, JWT and Multi-factor authentication (MFA)

**baseapp_referrals**: Models and utilities for user referrals

## [baseapp-reactions](baseapp-reactions)

Reusable app to enable User's reactions on any model, features like like/dislike or any other reactions type, customizable for project's needs.

## [baseapp-payments](baseapp-payments)

Utilities for payments

## [baseapp-drf-view-action-permissions](baseapp-drf-view-action-permissions)

This app uses django provided permission and group model and provides the ability to add roles to a django model, and make views from the [django-restframework](https://www.django-rest-framework.org/) check for them. A **Permission** represents the lowest single unit of access. A **Group** is a collection of Permissions. A **Role** can have many Permision Groups, many Permissions and many **Excluded Permissions**. The access of a Role is the aggregation of its single Permissions + the permissions on its **Permission** Groups - its Excluded Permissions.


## How to develop

Each module of baseapp-backend has a demo project in `testproject/` directory, which can be run as a standalone Django app to test. Then in baseapp-backend directory:

```bash
# create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install baseapp-core dependencies
pip3 install -r baseapp-core/testproject/requirements.txt

# Install baseapp-APPNAME dependencies
pip3 install -r baseapp-APPNAME/testproject/requirements.txt
```

Run testproject:

```bash
cd baseapp-APPNAME
python manage.py runserver
```

### Testing

Running unit tests:

```bash
pytest baseapp-APPNAME/baseapp_APPNAME/tests
```

### Implementation

The packages follow this structure for testing:

```
baseapp-APPNAME/
    manage.py
    testproject/
        settings.py
    baseapp_APPNAME/
        tests/
            pytest.ini
```

#### Minimum requires
- All app tests in `baseapp-APPNAME/baseapp_APPNAME/tests` directory
- A manage.py file in `baseapp-APPNAME` directory
  - You can copy that from baseapp-core
- A testproject directory in baseapp-APPNAME directory
- In the testproject dir:
  - A settings.py file
    - It can/should import `baseapp_core/tests/settings.py`
  - A requirements.txt file that installs "install_requires" of the tested app.
    - It must install app required packages:
      ```
      # install "install_requires" from setup.cfg
      -e ./baseapp-APPNAME
      ```
    - This file must only contain packages needed for testing. The `requirements.txt` in `baseapp-core/testproject` is being used as a based `requirements.txt` for testing. If necessary, it is possible to add more specific packages that are not already in `baseapp-core/testproject/requirements.txt`.
- In the `baseapp-APPNAME/tests dir`:
  - A pytest.ini that assigns the right settings:
  ```
  # In baseapp-APPNAME/baseapp_APPNAME/tests/pytest.ini

  [pytest]
  DJANGO_SETTINGS_MODULE = testproject.settings
  # -- recommended but optional:
  python_files = tests.py test_*.py *_tests.py
  ```
