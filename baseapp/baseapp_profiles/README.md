# BaseApp Profiles

Reusable app to handle profiles, URL's paths and metadata. It provides useful models and GraphQL Interfaces.

## How to install:

And install the package with `pip install baseapp-backend`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to use

Add `baseapp_profiles` to your project's `INSTALLED_APPS` and run `./manage.py migrate` as any other django model:

```python
INSTALLED_APPS = [
    'baseapp_profiles',
]
```

Add `baseapp_profiles.middleware.CurrentProfileMiddleware` to the `MIDDLEWARE` list in your django settings file, make sure it is **after** `django.contrib.auth.middleware.AuthenticationMiddleware`.

Add `baseapp_profiles.permissions.ProfilesPermissionsBackend` to the `AUTHENTICATION_BACKENDS` list in your django settings file.

Expose `ProfilesMutations` and `ProfilesQuery` in your GraphQL/graphene endpoint, like:

```python
from baseapp_profiles.graphql.mutations import ProfilesMutations
from baseapp_profiles.graphql.queries import ProfilesQuery

class Query(graphene.ObjectType, ProfilesQuery):
    pass

class Mutation(graphene.ObjectType, ProfilesMutations):
    pass

schema = graphene.Schema(query=Query, mutation=Mutation)
```

### ProfileInterface

`ProfileInterface` is a GraphQL interface that can be used to query for profiles. It has the following fields:

- `profile` return the `Profile` for the object

## How to develop

General development instructions can be found in [main README](..#how-to-develop).
