# BaseApp Backend

This repository contains baseapp django packages to be reused accross projects based on TSL's BaseApp

## [baseapp-core](baseapp_core)

The core contains the basics for BaseApp like Django Rest Framework's basic setup, custom ModelSerializer and fields, also base email template, testing helpers and other utilities. It also contains the base GraphQL setup, check [baseapp_core/graphql](baseapp_core/graphql) for more info.

## [baseapp-auth](baseapp_auth)

Reusable user and authentication utilities. Authentication setup using AuthToken, JWT and Multi-factor authentication (MFA)

## [baseapp-referrals](baseapp_referrals)

Models and utilities for user referrals

## [baseapp-cloudflare-stream-field](baseapp_cloudflare_stream_field)

Integration with Cloudflare Stream for file streaming

## [baseapp-drf-view-action-permissions](baseapp_drf_view_action_permissions)

This app uses django provided permission and group model and provides the ability to add roles to a django model, and make views from the [django-restframework](https://www.django-rest-framework.org/) check for them. A **Permission** represents the lowest single unit of access. A **Group** is a collection of Permissions. A **Role** can have many Permission Groups, many Permissions and many **Excluded Permissions**. The access of a Role is the aggregation of its single Permissions + the permissions on its **Permission** Groups - its Excluded Permissions.

## [baseapp-e2e](baseapp_e2e)

Utilities for performing E2E (End-To-End) tests with front-end client. (Database initialization and seeding)

## [baseapp-message-templates](baseapp_message_templates)

## [baseapp-notifications](baseapp_notifications)

Reusable app to handle in-app, email and push notifications.

## [baseapp-payments](baseapp_payments)

Utilities for payments

## [baseapp-reactions](baseapp_reactions)

Reusable app to enable User's reactions on any model, features like like/dislike or any other reactions type, customizable for project's needs.

## [baseapp-reports](baseapp_reports)

App to allow users to report other user generated content.

## [baseapp-blocks](baseapp_blocks)

Let a Profile block another Profile.

## [baseapp-ratings](baseapp_ratings)

Rate from 0 to N on any model. With support for average ratings.

## [baseapp-social-auth](baseapp_social_auth)

Login/signup using social networks (Facebook, Google and others)

## [baseapp-url-shortening](baseapp_url_shortening)

Functionality for url shortening

## [baseapp-follows](baseapp_follows)

Reusable app to enable any model follow/unfollow any model.

## [baseapp-pages](baseapp_pages)

Reusable app to handle pages, URL's paths and metadata. It provides useful models and GraphQL Interfaces.

## [baseapp-wagtail](baseapp_wagtail)

Wagtail CMS integration with BaseApp

## [baseapp-comments](baseapp_comments)

Comment threads on any model. With support for reactions, notifications and GraphQL subscriptions.

## [baseapp-organizations](baseapp_organizations)

Reusable app to handle organizations. Users can have and manage multiple Organizations.

## [baseapp-chats](baseapp_chats)

Real-time chat between users, and groups of users.

## [baseapp-profiles](baseapp_profiles)

This app provides user profile management functionalities, allowing users to create, update, and manage their profiles. Allowing the user to manage multiple profiles and act as a profile when commenting, posting, etc.

## [baseapp.activity_log](baseapp/activity_log)
 
Reusable app to handle activity logs.

## [baseapp.content_feed](baseapp/content_feed)

Reusable app to handle content feeds.

## How to develop

Each module of baseapp-backend has a demo project in `testproject/` directory, which can be run as a standalone Django app to test. Then in baseapp-backend directory:

```bash
# Bring up docker containers
docker compose up -d --wait

# Enter db container
docker compose exec db bash

# Create 'backend' database
psql -U postgres -c 'create database backend;'

# Exit db container
exit

# Enter backend docker container
docker compose exec backend bash
```

If you're switching between projects and you want to wipe the DB you can do
```
psql -U postgres -c 'drop database backend;'
psql -U postgres -c 'create database backend;'
```

Run testproject inside the backend docker container:

```bash
# Install baseapp-backend's testproject dependencies
pip3 install -r testproject/requirements.txt

# Change folder to your app's testproject:
cd baseapp
python manage.py runserver 0.0.0.0:8000
```

### How to develop with a specific project

Clone the repository inside your project's backend dir:

```bash
git clone git@github.com:silverlogic/baseapp-backend.git
```

And manually install the package:

```bash
pip install -e baseapp-backend
```

The `-e` flag will make it like any change you make in the cloned files will effect into the project, even with django's auto reload.

### Getting auto complete to work

Currently there's an issue with Pylance where it can't properly detect package installed in the editable mode with pip (eg. pip install -e ./baseapp-core)

To get around this, I've read online that adding `--config-settings editable_mode=strict` to each line of an editable install will work,
but I did not find that to be the case on my machine, instead I would recommend explicitly adding the package directories to the path for pylance

To do this, assuming you've opened the folder at the root of the repo, just add to your `.vscode/settings.json` file this
```
"python.analysis.extraPaths": [
    "./baseapp-auth",
    "./baseapp-blocks",
    "./baseapp-chats",
    "./baseapp-cloudflare-stream-field",
    "./baseapp-comments",
    "./baseapp-content-feed",
    "./baseapp-core",
    "./baseapp-drf-view-action-permissions",
    "./baseapp-e2e",
    "./baseapp-follows",
    "./baseapp-message-templates",
    "./baseapp-notifications",
    "./baseapp-pages",
    "./baseapp-payments",
    "./baseapp-profiles",
    "./baseapp-ratings",
    "./baseapp-reactions",
    "./baseapp-reports",
    "./baseapp-social-auth",
    "./baseapp-url-shortening",
]
```

### Testing

Running unit tests:

```bash
docker compose exec backend pytest baseapp_APPNAME/tests
```

### Implementation

The packages follow this structure for testing:

```
baseapp/
    manage.py
    testproject/
        settings.py
    baseapp_APPNAME/
        tests/
```

#### Minimum requires

- All app tests in `baseapp_APPNAME/tests` directory
- In the testproject dir:
  - Change the settings.py file to enable your app
    - Add your app to the `INSTALLED_APPS` list
  - If your app needs a new dependency, add it to the "extras_require" of the main `setup.cfg`.
    - Change `testproject/requirements.txt` to include your new dependency from your "extras_require" using `pip install -e .[your_extra]`

## Publishing baseapp-backend package to pypi registry

To publish a new version to pypi you need to:

- make sure that builds pass
- create a release on github
  - choose to create a new tag (named as `baseapp@v<version>` e.g. baseapp@v1.2.3)
  - use the same name for release title
  - optionally add changelog text
