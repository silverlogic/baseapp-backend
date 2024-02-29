# BaseApp Backend

This repository contains baseapp django packages to be reused accross projects based on TSL's BaseApp

## [baseapp-core](baseapp-core)

The core contains the basics for BaseApp like Django Rest Framework's basic setup, custom ModelSerializer and fields, also base email template, testing helpers and other utilities. It also contains the base GraphQL setup, check [baseapp-core/graphql](baseapp-core/graphql) for more info.

## [baseapp-auth](baseapp-auth)

Contains the following apps:

**baseapp_auth**: Reusable user and authentication utilities. Authentication setup using AuthToken, JWT and Multi-factor authentication (MFA)

**baseapp_referrals**: Models and utilities for user referrals

## [baseapp-cloudflare-stream-field](baseapp-cloudflare-stream-field)

Integration with Cloudflare Stream for file streaming

## [baseapp-drf-view-action-permissions](baseapp-drf-view-action-permissions)

This app uses django provided permission and group model and provides the ability to add roles to a django model, and make views from the [django-restframework](https://www.django-rest-framework.org/) check for them. A **Permission** represents the lowest single unit of access. A **Group** is a collection of Permissions. A **Role** can have many Permision Groups, many Permissions and many **Excluded Permissions**. The access of a Role is the aggregation of its single Permissions + the permissions on its **Permission** Groups - its Excluded Permissions.

## [baseapp-e2e](baseapp-e2e)

Utilities for performing E2E (End-To-End) tests with front-end client. (Database initialization and seeding)

## [baseapp-message-templates](baseapp-message-templates)

## [baseapp-notifications](baseapp-notifications)

Reusable app to handle in-app, email and push notifications.

## [baseapp-payments](baseapp-payments)

Utilities for payments

## [baseapp-reactions](baseapp-reactions)

Reusable app to enable User's reactions on any model, features like like/dislike or any other reactions type, customizable for project's needs.

## [baseapp-social-auth](baseapp-social-auth)

Login/signup using social networks (Facebook, Google and others)

## [baseapp-url-shortening](baseapp-url-shortening)

Functionality for url shortening

## [baseapp-follows](baseapp-follows)

Reusable app to enable any model follow/unfollow any model.

## [baseapp-pages](baseapp-pages)

Reusable app to handle pages, URL's paths and metadata. It provides useful models and GraphQL Interfaces.

## How to develop

Each module of baseapp-backend has a demo project in `testproject/` directory, which can be run as a standalone Django app to test. Then in baseapp-backend directory:

```bash
# Bring up docker containers
docker compose up -d --wait

# Enter backend docker container
docker compose exec backend bash
```

Run testproject inside the backend docker container:

```bash
# Install baseapp-APPNAME dependencies
pip3 install -r baseapp-APPNAME/testproject/requirements.txt

# Change folder to your app's testproject:
cd baseapp-APPNAME/testproject
python manage.py runserver
```

### How to develop with a specific project

Clone the repository inside your project's backend dir:

```bash
git clone git@github.com:silverlogic/baseapp-backend.git
```

And manually install the package:

```bash
pip install -e baseapp-backend/baseapp-APPNAME
```

The `-e` flag will make it like any change you make in the cloned files will effect into the project, even with django's auto reload.

### Testing

Running unit tests:

```bash
docker compose exec backend pytest baseapp-APPNAME/baseapp_APPNAME/tests
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
