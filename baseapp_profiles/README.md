# BaseApp Profiles

Reusable app to handle profiles, URL's paths and metadata. It provides useful models and GraphQL Interfaces.

## How to install:

And install the package with `pip install baseapp-backend`.

If you want to develop, [install using this other guide](#how-to-develop).

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

## ProfilableModel

`ProfilableModel` is an abstract model mixin that automatically keeps a `Profile` in sync with your model via PostgreSQL triggers — no Python signals required.

### What it does

- **On INSERT**: if `profile_owner_sql` is defined, a trigger creates a `Profile` row and links it back to your model via the `profile` FK (uses `ON CONFLICT … DO UPDATE` so it is safe to re-run).
- **On UPDATE**: a trigger updates `profile.name` whenever the columns referenced in `profile_name_sql` change.

Both triggers are registered automatically at class-definition time — no manual wiring needed.

### Usage

Inherit from `ProfilableModel` and define at least `profile_name_sql`:

```python
from baseapp_profiles.models import ProfilableModel

class MyModel(ProfilableModel):
    # Required: SQL expression using NEW.<col> references that produces the profile name.
    # NULL-safe — COALESCE and TRIM are applied automatically.
    profile_name_sql = "NEW.first_name || ' ' || NEW.last_name"

    # Optional: SQL expression for the profile owner_id on INSERT.
    # When provided, the trigger creates and links a Profile automatically.
    # Omit when ownership is determined later by application logic (e.g. Organization).
    profile_owner_sql = "NEW.id"
```

After adding or changing these attributes, run `makemigrations` to capture the updated trigger SQL:

```bash
./manage.py makemigrations
```

### Signals

Two post-save signal handlers are available for features that still require Python-level logic:

- **`create_profile_url_path`** — calls `profile.create_url_path()` after creation when `baseapp_pages` is installed. Connect it if your model needs URL paths:

  ```python
  from django.db.models.signals import post_save
  from baseapp_profiles.signals import create_profile_url_path

  post_save.connect(create_profile_url_path, sender=MyModel)
  ```

- **`update_user_profile`** *(deprecated)* — fallback for projects that have not yet added `profile_owner_sql`. Creates the profile via Python if the trigger did not run. New projects should use `profile_owner_sql` instead.

### ProfileInterface

`ProfileInterface` is a GraphQL interface that can be used to query for profiles. It has the following fields:

- `profile` return the `Profile` for the object

## How to develop

General development instructions can be found in [main README](..#how-to-develop).
